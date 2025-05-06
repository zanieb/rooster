from pathlib import Path
from typing import Generator

import pygit2 as git
from packaging.version import Version

from rooster._config import Config

TAG_PREFIX = "refs/tags/"


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


def get_commit_for_tag(
    repo: git.repository.Repository,
    tag: str,
) -> git.Commit:
    commit = repo.lookup_reference(TAG_PREFIX + tag).peel()
    return commit


def get_initial_commit(repo: git.repository.Repository) -> git.Commit:
    """
    Get the initial commit of the repository.
    """
    # Walk the repository to find the initial commit
    for commit in repo.walk(repo.head.target):
        if commit.parents == []:
            return commit
    raise GitLookupError("Could not find initial commit")


def get_submodule_commit(
    repo: git.repository.Repository,
    at_commit: git.Commit | None,
    submodule: git.repository.Repository,
) -> git.Commit:
    if not at_commit:
        return get_latest_commit(submodule)

    # Get the tree at that commit
    tree = at_commit.tree

    # Find the submodule entry in the tree
    try:
        path_parts = Path(submodule.workdir).relative_to(repo.workdir).parts
        current_tree = tree

        for i, part in enumerate(path_parts):
            if i == len(path_parts) - 1:
                entry = current_tree[part]
                if entry.type_str == "commit":
                    return entry
                else:
                    raise ValueError(f"{submodule.workdir} is not a submodule")
            else:
                entry = current_tree[part]
                if entry.type_str != "tree":
                    raise ValueError(f"Path component {part} is not a directory")
                current_tree = repo.get(entry.id)
    except KeyError:
        raise ValueError(f"Submodule {submodule} not found at commit {at_commit.id}")

    raise ValueError(f"Could not find submodule {submodule.workdir}")


def get_commits_between_commits(
    repo: git.repository.Repository,
    old_commit: git.Commit | None,
    new_commit: git.Commit | None,
) -> Generator[git.Commit, None, None]:
    """
    Yield all commits between two commits, inclusive of the new commit but not
    the old commit.

    If the old commit is `None`, the initial commit will be used.
    If the new commit is `None`, HEAD will be used.
    """
    yield new_commit

    # Walk backwards from the second commit until we find the first commit
    for commit in repo.walk(new_commit.id if new_commit else None):
        if (
            old_commit
            and commit.id == old_commit.id
            or commit.id == "d07eefc408a59baa324541261b12f395e38b9344"
        ):
            break
        yield commit
    else:
        if old_commit and new_commit:
            raise GitLookupError(
                f"Could not find commit {old_commit.id} in ancestors of {new_commit.id}; is {old_commit.id} on a different branch?"
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
