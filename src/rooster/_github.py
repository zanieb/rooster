import dataclasses
import functools
import os
import re
import shutil
import subprocess
import sys
import textwrap

import httpx

from rooster._cache import cached_graphql_client
from rooster._git import git

TOKEN_REGEX = re.compile(r"Token:\s(.*)")


@dataclasses.dataclass(frozen=True, unsafe_hash=True)
class PullRequest:
    title: str
    number: int
    labels: frozenset[str]
    author: str
    repo_name: str
    repo_owner: str

    @property
    def url(self):
        return (
            f"https://github.com/{self.repo_owner}/{self.repo_name}/pull/{self.number}"
        )

    def __lt__(self, other):
        return self.number < other.number


@dataclasses.dataclass(frozen=True, unsafe_hash=True)
class Release:
    id: str
    name: str
    tag: str
    body: str
    draft: bool
    prerelease: bool


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
        ["gh", "auth", "status", "--show-token"], capture_output=True
    )
    output = gh_auth_status.stdout.decode()
    if not gh_auth_status.returncode == 0:
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
    if response.get("errors"):
        raise RuntimeError(f"GraphQL server responded with error: {response['errors']}")
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
    if repo.endswith(".git"):
        repo = repo[:-4]
    return owner, repo


def get_pull_requests_for_commits(
    owner, repo_name, commits: list[git.Commit]
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
    seen_commits = 0
    expected_commits = {str(commit.id) for commit in commits}

    query = textwrap.dedent(
        """
        query associatedPullRequest(
            $repo: String!, $owner: String!, $commit: String!, $after: String
        ) {
            repository(name: $repo, owner: $owner) {
                commit: object(expression: $commit) {
                    ... on Commit {
                        id
                        history(after: $after) {
                            nodes {
                                oid
                                associatedPullRequests(first: 1) {
                                    edges {
                                        node {
                                            title
                                            number
                                            author {
                                                login
                                            }
                                            labels(first: 10) {
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
        first_commit = commits[0]
        page_start = None

        next_page = True
        while next_page and seen_commits < len(commits):
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

            response_commits = response["data"]["repository"]["commit"]["history"][
                "nodes"
            ]
            seen_commits += len(response_commits)
            for commit in response_commits:
                if commit["oid"] not in expected_commits:
                    continue

                associated_pull_requests = commit["associatedPullRequests"]["edges"]
                if not associated_pull_requests:
                    # TODO: Commits without pull requests should probably be included in
                    #       the changelog with a link to the commit and the commit
                    #       message with an opt-in
                    continue

                for item in associated_pull_requests:
                    pull_request = item["node"]
                    if not pull_request:
                        continue
                    labels = {
                        edge["node"]["name"] for edge in pull_request["labels"]["edges"]
                    }

                    pull_requests.append(
                        PullRequest(
                            title=pull_request["title"],
                            number=pull_request["number"],
                            labels=frozenset(labels),
                            author=pull_request["author"]["login"],
                            repo_name=repo_name,
                            repo_owner=owner,
                        )
                    )

            page_info = response["data"]["repository"]["commit"]["history"]["pageInfo"]
            next_page = page_info["hasNextPage"]
            page_start = page_info["endCursor"]

    return pull_requests


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
    return
