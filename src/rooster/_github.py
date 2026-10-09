import dataclasses
import functools
import os
import re
import shutil
import subprocess
import sys
import textwrap
from collections.abc import Sequence
from typing import Protocol, Self

import httpx

from rooster._cache import cached_graphql_client

TOKEN_REGEX = re.compile(r"Token:\s(.*)")
NUMBER_REGEX = re.compile(r"\(#([1-9][0-9]*)\)\s*$")


class Commit(Protocol):
    @property
    def id(self) -> object: ...


@dataclasses.dataclass(frozen=True, unsafe_hash=True)
class PullRequest:
    title: str
    number: int
    labels: frozenset[str]
    author: str
    repo_name: str
    repo_owner: str
    url: str

    def __lt__(self, other):
        return self.number < other.number

    def with_title(self, title: str) -> Self:
        return dataclasses.replace(self, title=title)


@dataclasses.dataclass(frozen=True, unsafe_hash=True)
class Release:
    id: str
    name: str
    tag: str
    body: str
    draft: bool
    prerelease: bool


class GitHubGraphQLError(RuntimeError):
    def __init__(self, errors: list[dict]):
        self.errors = errors
        super().__init__(f"GraphQL server responded with error: {errors}")


@functools.cache
def get_github_token() -> str:
    """
    Retrieve the current GitHub token from the `gh` CLI or `GITHUB_TOKEN` environment variable.

    This function is cached and should only run once invocation of `rooster`.
    """
    if "GITHUB_TOKEN" in os.environ:
        return os.environ["GITHUB_TOKEN"]

    if not shutil.which("gh"):
        print(
            "You must provide a GitHub access token via GITHUB_TOKEN or have the gh CLI"
            " installed."
        )
        raise RuntimeError("Failed to retrieve GitHub token")

    gh_auth_status = subprocess.run(
        ["gh", "auth", "status", "--show-token"], capture_output=True, check=False
    )
    output = gh_auth_status.stdout.decode()
    if gh_auth_status.returncode != 0:
        print(
            "Failed to retrieve authentication status from GitHub CLI:", file=sys.stderr
        )
        print(output, file=sys.stderr)
        raise RuntimeError("Failed to retrieve GitHub token")

    match = TOKEN_REGEX.search(output)
    if not match:
        print(
            (
                "Failed to find token in GitHub CLI output with regex"
                f" {TOKEN_REGEX.pattern!r}:"
            ),
            file=sys.stderr,
        )
        print(output, file=sys.stderr)
        raise RuntimeError("Failed to retrieve GitHub token")

    return match.groups()[0]


def _graphql(client: httpx.Client, query: str, variables: dict[str, object]):
    """
    Perform a GitHub GraphQL request.
    """
    github_token = get_github_token()

    response = (
        client.post(
            "https://api.github.com/graphql",
            json={"query": query, "variables": variables},
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {github_token}",
            },
        )
        .raise_for_status()
        .json()
    )
    if errors := response.get("errors"):
        raise GitHubGraphQLError(errors)
    return response


def parse_remote_url(remote_url: str) -> tuple[str, str]:
    """
    Parse a Git remote URL into owner and repository components.
    """
    ssh_prefix = "git@github.com:"
    if remote_url.startswith(ssh_prefix):
        owner_slash_repo = remote_url[len(ssh_prefix) :]
        owner, repo = owner_slash_repo.split("/")
    else:
        parts = remote_url.split("/")
        owner = parts[-2]
        repo = parts[-1]
    repo = repo.removesuffix(".git")
    return owner, repo


def get_pull_requests_for_commits(
    owner, repo_name, commits: Sequence[Commit]
) -> list[PullRequest]:
    """
    Retrieve the corresponding pull requests for a list of commits.

    Pull requests are retrieved in bulk, but GitHub enforces a page size of ~100 items
    so multiple HTTP requests may be made to retrieve all pull requests.

    This method [caches](`rooster._cache`) responses from GitHub to disk to avoid
    excessive requests on repeated invocations of `rooster`.
    """
    if not commits:
        return []

    pull_requests = []
    referenced_pull_requests: dict[tuple[int, str], PullRequest | None] = {}
    expanded_pull_requests: set[int] = set()
    unresolved_commits: list[tuple[str, PullRequest]] = []
    seen_commits = 0
    expected_commits = {str(commit.id) for commit in commits}

    # Note we use `first: 10` on `history` because GitHub can otherwise
    # encounter an internal timeout and return a 502
    query = textwrap.dedent(
        """
        query associatedPullRequest(
            $repo: String!, $owner: String!, $commit: String!, $after: String
        ) {
            repository(name: $repo, owner: $owner) {
                commit: object(expression: $commit) {
                    ... on Commit {
                        id
                        history(first: 10, after: $after) {
                            nodes {
                                oid
                                message
                                associatedPullRequests(first: 1) {
                                    edges {
                                        node {
                                            title
                                            number
                                            url
                                            author {
                                                login
                                            }
                                            labels(first: 100) {
                                                edges {
                                                    node {
                                                        name
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                            pageInfo {
                                hasNextPage
                                endCursor
                            }
                        }
                    }
                }
            }
        }
        """
    )

    with cached_graphql_client() as client:
        page_start = None
        response_commits = None
        next_page = True

        # Find the first commit on the remote
        response_commits = []
        commit_index = 0
        while not response_commits and commit_index < len(commits):
            first_commit = commits[commit_index]
            commit_index += 1
            response = _graphql(
                client,
                query,
                variables={
                    "owner": owner,
                    "repo": repo_name,
                    "commit": str(first_commit.id),
                    "after": page_start,
                },
            )
            response_commits = response["data"]["repository"]["commit"]

        # Then paginate through the commits
        while next_page and seen_commits < len(commits):
            response_commits = response["data"]["repository"]["commit"]
            if not response_commits:
                break

            response_commits = response_commits["history"]["nodes"]
            seen_commits += len(response_commits)
            for commit in response_commits:
                if commit["oid"] not in expected_commits:
                    continue

                associated = next(
                    (
                        item["node"]
                        for item in commit["associatedPullRequests"]["edges"]
                        if item["node"]
                    ),
                    None,
                )
                pull_request = (
                    _pull_request_from_node(associated, owner, repo_name)
                    if associated
                    else None
                )

                # A rebase can associate a squash commit with the PR that
                # integrated its branch. The subject still identifies the
                # original PR; references in the body may describe other work.
                subject = commit["message"].partition("\n")[0]
                match = NUMBER_REGEX.search(subject)
                if match:
                    number = int(match[1])
                    if pull_request and pull_request.number == number:
                        pull_requests.append(pull_request)
                        continue
                    reference = (number, subject)
                    if reference not in referenced_pull_requests:
                        referenced_pull_requests[reference] = (
                            get_pull_request_by_number(
                                client, owner, repo_name, number, subject
                            )
                        )
                    original = referenced_pull_requests[reference]
                    if original:
                        pull_requests.append(original)
                        if pull_request:
                            expanded_pull_requests.add(pull_request.number)
                        continue
                    print(
                        f"Warning: could not match commit {commit['oid']} to merged "
                        f"pull request #{number} in {owner}/{repo_name}.",
                        file=sys.stderr,
                    )

                if pull_request:
                    pull_requests.append(pull_request)
                    if not match:
                        unresolved_commits.append((commit["oid"], pull_request))

            # Get the next response
            page_info = response["data"]["repository"]["commit"]["history"]["pageInfo"]
            next_page = page_info["hasNextPage"]
            page_start = page_info["endCursor"]
            if not next_page or seen_commits >= len(commits):
                break

            response = _graphql(
                client,
                query,
                variables={
                    "owner": owner,
                    "repo": repo_name,
                    "commit": str(first_commit.id),
                    "after": page_start,
                },
            )

    for commit_id, pull_request in unresolved_commits:
        if pull_request.number in expanded_pull_requests:
            print(
                f"Warning: could not identify the original pull request for "
                f"commit {commit_id}; using {pull_request.url}. "
                "Check this commit when reviewing the changelog.",
                file=sys.stderr,
            )

    return pull_requests


def _pull_request_from_node(node: dict, owner: str, repo_name: str) -> PullRequest:
    return PullRequest(
        title=node["title"],
        number=node["number"],
        labels=frozenset(edge["node"]["name"] for edge in node["labels"]["edges"]),
        author=node["author"]["login"] if node["author"] else "ghost",
        repo_name=repo_name,
        repo_owner=owner,
        url=node["url"],
    )


def get_release(repo_org: str, repo_name: str, tag_name: str) -> Release | None:
    github_token = get_github_token()
    try:
        release = (
            httpx.get(
                f"https://api.github.com/repos/{repo_org}/{repo_name}/releases/tags/{tag_name}",
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {github_token}",
                },
            )
            .raise_for_status()
            .json()
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return None
        raise

    return Release(
        id=release["id"],
        name=release["name"],
        tag=release["tag_name"],
        body=release["body"],
        draft=release["draft"],
        prerelease=release["prerelease"],
    )


def update_release_notes(
    repo_org: str, repo_name: str, release_id: str, content: str
) -> None:
    github_token = get_github_token()
    request = {"body": content}
    response = httpx.patch(
        f"https://api.github.com/repos/{repo_org}/{repo_name}/releases/{release_id}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {github_token}",
        },
        json=request,
    )
    response.raise_for_status()


def get_pull_request_by_number(
    client: httpx.Client, owner: str, repo_name: str, number: int, subject: str
) -> PullRequest | None:
    """
    Retrieve a merged pull request whose merge commit or title matches the subject.
    """
    query = textwrap.dedent(
        """
        query pullRequestByNumber($repo: String!, $owner: String!, $number: Int!) {
            repository(name: $repo, owner: $owner) {
                pullRequest(number: $number) {
                    title
                    number
                    url
                    merged
                    mergeCommit {
                        message
                    }
                    author {
                        login
                    }
                    labels(first: 100) {
                        edges {
                            node {
                                name
                            }
                        }
                    }
                }
            }
        }
        """
    )

    try:
        response = _graphql(
            client,
            query,
            variables={"owner": owner, "repo": repo_name, "number": number},
        )
    except GitHubGraphQLError as exc:
        if all(
            error.get("type") == "NOT_FOUND"
            and error.get("path") == ["repository", "pullRequest"]
            for error in exc.errors
        ):
            return None
        raise

    pull_request = response["data"]["repository"]["pullRequest"]
    if not pull_request or not pull_request["merged"]:
        return None
    merge_commit = pull_request["mergeCommit"]
    # GitHub may not resolve the merge commit of an older merged PR. Its title
    # still provides a check against references to unrelated pull requests.
    expected_subject = (
        merge_commit["message"].partition("\n")[0]
        if merge_commit
        else f"{pull_request['title']} (#{number})"
    )
    if expected_subject != subject:
        return None
    return _pull_request_from_node(pull_request, owner, repo_name)
