import subprocess

import pytest

from rooster._git import (
    GitLookupError,
    get_commits_between_commits,
    get_latest_commit,
    get_submodule_commit,
    repo_from_path,
)
from rooster._testing import git_directory


def git(directory, *args):
    return subprocess.check_output(["git", *args], cwd=directory, text=True).strip()


def commit(directory, message):
    git(directory, "commit", "--allow-empty", "-m", message)
    return get_latest_commit(repo_from_path(directory))


def test_commit_range_matches_git_revision_range(git_directory):
    old = commit(git_directory, "Released")
    first = commit(git_directory, "First change")
    head = commit(git_directory, "Second change")
    repo = repo_from_path(git_directory)

    assert [c.id for c in get_commits_between_commits(repo, old, head)] == [
        head.id,
        first.id,
    ]
    assert list(get_commits_between_commits(repo, head, head)) == []
    assert {c.id for c in get_commits_between_commits(repo, None, head)} == {
        old.id,
        first.id,
        head.id,
    }


def test_commit_range_includes_merged_history(git_directory):
    commit(git_directory, "Root")
    git(git_directory, "switch", "-c", "feature")
    feature = commit(git_directory, "Feature")
    git(git_directory, "switch", "main")
    old = commit(git_directory, "Released")
    git(git_directory, "merge", "--no-ff", "feature", "-m", "Merge feature")
    repo = repo_from_path(git_directory)
    head = get_latest_commit(repo)

    actual = [str(c.id) for c in get_commits_between_commits(repo, old, head)]
    expected = git(git_directory, "rev-list", f"{old.id}..{head.id}").splitlines()
    assert set(actual) == set(expected) == {str(feature.id), str(head.id)}
    assert len(actual) == len(set(actual))


def test_commit_range_rejects_unrelated_base(git_directory):
    commit(git_directory, "Root")
    git(git_directory, "switch", "-c", "feature")
    old = commit(git_directory, "Feature")
    git(git_directory, "switch", "main")
    head = commit(git_directory, "Main")

    with pytest.raises(GitLookupError, match="different branch"):
        list(get_commits_between_commits(repo_from_path(git_directory), old, head))


def test_submodule_revision_uses_the_submodule_object_database(git_directory):
    before = commit(git_directory, "Before submodule")
    path = git_directory / "vendor" / "dep"
    path.mkdir(parents=True)
    git(path, "init", "-b", "main")
    git(path, "config", "user.name", "Test User")
    git(path, "config", "user.email", "test@example.com")
    included = commit(path, "Included dependency revision")
    git(
        git_directory,
        "update-index",
        "--add",
        "--cacheinfo",
        f"160000,{included.id},vendor/dep",
    )
    parent = commit(git_directory, "Add submodule")
    commit(path, "Unrecorded dependency revision")
    repo = repo_from_path(git_directory)
    submodule = repo_from_path(path)

    found = get_submodule_commit(repo, parent, submodule)

    assert found is not None
    assert found.id == included.id
    assert found.message == "Included dependency revision\n"
    assert get_submodule_commit(repo, before, submodule) is None
    assert get_submodule_commit(repo, None, submodule) is None
