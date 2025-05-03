import logging

from pathlib import Path
from typing import Generator

import pygit2 as git
from packaging.version import Version

from rooster._config import Config

TAG_PREFIX = "refs/tags/"

logger = logging.getLogger(__name__)


class GitLookupError(Exception):
    """
    Error when looking up a requested git object.
    """


def repo_from_path(target: Path) -> git.repository.Repository:
    return git.repository.Repository(target.absolute())


def get_tags(config: Config, repo: git.repository.Repository) -> list[str]:
    references = repo.listall_references()
    return [
        _parse_tag_reference(config, ref)
        for ref in references
        if ref.startswith(TAG_PREFIX + config.version_tag_prefix)
    ]


def _parse_tag_reference(config: Config, reference: str) -> str:
    return reference[len(TAG_PREFIX + config.version_tag_prefix) :]


def get_commit_for_version(
    config: Config,
    repo: git.repository.Repository,
    version: Version,
) -> git.Commit:
    commit = repo.lookup_reference(
        TAG_PREFIX + config.version_tag_prefix + str(version)
    ).peel()
    return commit


def get_submodule_commit(
    repo: git.repository.Repository, at_commit: git.Commit, submodule: Path
) -> git.Commit:
    # Get the tree at that commit
    tree = at_commit.tree

    # Find the submodule entry in the tree
    # The following written by an LLM — may not be needed
    try:
        path_parts = submodule.parts
        current_tree = tree

        for i, part in enumerate(path_parts):
            if i == len(path_parts) - 1:
                entry = current_tree[part]
                if entry.type_str == "commit":
                    return entry
                else:
                    raise ValueError(f"{submodule} is not a submodule")
            else:
                entry = current_tree[part]
                if entry.type_str != "tree":
                    raise ValueError(f"Path component {part} is not a directory")
                current_tree = repo.get(entry.id)
    except KeyError:
        raise ValueError(f"Submodule {submodule} not found at commit {at_commit.id}")

    raise ValueError(f"Could not find submodule {submodule}")


def get_commits_between_versions(
    config: Config,
    target: Path,
    first_version: Version | None = None,
    second_version: Version | None = None,
) -> Generator[git.Commit, None, None]:
    """
    Yield all commits between two tags
    """
    repo = git.repository.Repository(target.absolute())
    first_commit = (
        get_commit_for_version(config, repo, first_version).id
        if first_version is not None
        else None
    )
    second_commit = (
        get_commit_for_version(config, repo, second_version).id
        if second_version is not None
        # TODO: Lookup main branch
        else get_latest_commit(repo)
    )
    return get_commits_between_commits(
        target,
        first_commit,
        second_commit,
    )


def get_commits_between_commits(
    repo: git.repository.Repository,
    first_commit: git.Commit,
    second_commit: git.Commit | None,
) -> Generator[git.Commit, None, None]:
    """
    Yield all commits between two tags
    """
    # Walk backwards from the second commit until we find the first commit
    for commit in repo.walk(second_commit.id):
        if commit.id == first_commit.id:
            break
        yield commit
    else:
        if first_commit:
            raise GitLookupError(
                f"Could not find commit {first_commit.id} in ancestors of {second_commit.id}; is the {first_commit.id} on a different branch?"
            )


def get_submodule_commits_between_commits(
    repo: git.repository.Repository,
    submodule: Path,
    first_commit: git.Commit,
    second_commit: git.Commit,
):
    first_submodule_commit = get_submodule_commit(repo, first_commit, submodule)
    second_submodule_commit = get_submodule_commit(repo, second_commit, submodule)

    return get_commits_between_commits(
        repo_from_path(submodule),
        first_submodule_commit,
        second_submodule_commit,
    )


def get_remote_url(
    repo: git.repository.Repository, remote_name: str = "origin"
) -> str | None:
    names = {remote.name for remote in repo.remotes}
    if remote_name not in names:
        return None
    return repo.remotes[remote_name].url


def get_latest_commit(repo: git.repository.Repository) -> git.Commit:
    return repo.revparse_single("HEAD")
