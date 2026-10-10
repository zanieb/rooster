import subprocess
import tomllib

import pytest

from rooster._cli import release
from rooster._github import PullRequest
from rooster._testing import empty_commit, git_directory
from tests.test_git import commit, git


def project_with_change(directory, github_api, *, labels=(), config=""):
    (directory / "pyproject.toml").write_text(
        '[project]\nname = "example"\nversion = "1.2.3"\n' + config
    )
    subprocess.check_call(
        ["git", "remote", "add", "origin", "https://github.com/owner/repo"],
        cwd=directory,
    )
    empty_commit(directory, "Released")
    subprocess.check_call(["git", "tag", "1.2.3"], cwd=directory)
    empty_commit(directory, "Change 1 (#1)")
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=directory, text=True
    ).strip()
    github_api.commit(
        "Change 1 (#1)", github_api.pull_request(1, labels=labels), oid=head
    )


@pytest.mark.parametrize(
    ("labels", "expected"),
    [
        (("breaking", "feature"), "2.0.0"),
        (("breaking",), "2.0.0"),
        (("feature",), "1.3.0"),
        (("fix",), "1.2.4"),
    ],
)
def test_largest_label_bump_wins(git_directory, github_api, labels, expected, capsys):
    project_with_change(git_directory, github_api, labels=labels)

    release(directory=git_directory, update_version_files=False)

    assert f"Using new version {expected}" in capsys.readouterr().out


@pytest.mark.parametrize(
    "config",
    [
        "",
        '[tool.rooster]\nversion-files = ["pyproject.toml"]\n',
        '[tool.rooster]\nversion-files = [{path = "pyproject.toml", format = "toml", field = "project.version"}]\n',
    ],
)
def test_version_files_are_relative_to_project(
    git_directory, github_api, monkeypatch, config
):
    project_with_change(git_directory, github_api, config=config)
    caller = git_directory / "caller"
    caller.mkdir()
    unrelated = caller / "pyproject.toml"
    unrelated.write_text('[project]\nversion = "1.2.3"\n')
    monkeypatch.chdir(caller)

    release(directory=git_directory)

    project = tomllib.loads((git_directory / "pyproject.toml").read_text())
    assert project["project"]["version"] == "1.2.4"
    assert tomllib.loads(unrelated.read_text())["project"]["version"] == "1.2.3"


def test_first_release_includes_the_root_commit(git_directory, github_api, capsys):
    subprocess.check_call(
        ["git", "remote", "add", "origin", "https://github.com/owner/repo"],
        cwd=git_directory,
    )
    commits = []
    for number in [1, 2]:
        empty_commit(git_directory, f"Change {number} (#{number})")
        commits.append(
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=git_directory, text=True
            ).strip()
        )
    for number, oid in reversed(list(enumerate(commits, start=1))):
        github_api.commit(
            f"Change {number} (#{number})", github_api.pull_request(number), oid=oid
        )

    release(directory=git_directory, update_version_files=False)

    assert "Found 2 commits in the project" in capsys.readouterr().out
    changelog = (git_directory / "CHANGELOG.md").read_text()
    assert "[#1]" in changelog
    assert "[#2]" in changelog


def test_release_uses_recorded_submodule_revision(
    git_directory, github_api, monkeypatch
):
    project_with_change(
        git_directory,
        github_api,
        config='[tool.rooster]\nsubmodules = ["vendor/dep"]\n',
    )
    path = git_directory / "vendor" / "dep"
    path.mkdir(parents=True)
    git(path, "init", "-b", "main")
    git(path, "config", "user.name", "Test User")
    git(path, "config", "user.email", "test@example.com")
    git(path, "remote", "add", "origin", "https://github.com/owner/dep")
    included = commit(path, "Included")
    git(
        git_directory,
        "update-index",
        "--add",
        "--cacheinfo",
        f"160000,{included.id},vendor/dep",
    )
    commit(git_directory, "Record submodule")
    commit(path, "Not included")
    calls = {}

    def collect(owner, name, commits):
        calls[name] = [c.id for c in commits]
        return [
            PullRequest(
                "Change",
                1,
                frozenset(),
                "author",
                name,
                owner,
                f"https://github.com/{owner}/{name}/pull/1",
            )
        ]

    monkeypatch.setattr("rooster._cli.get_pull_requests_for_commits", collect)

    release(directory=git_directory, update_version_files=False)

    assert calls["dep"] == [included.id]


def test_rebased_breaking_change_bumps_minor_version(git_directory, github_api, capsys):
    (git_directory / "pyproject.toml").write_text(
        """
[tool.rooster]
major-labels = []
minor-labels = ["breaking"]
ignore-labels = ["release"]
"""
    )
    subprocess.check_call(
        ["git", "remote", "add", "origin", "https://github.com/owner/repo"],
        cwd=git_directory,
    )
    empty_commit(git_directory, "Previous release")
    subprocess.check_call(["git", "tag", "0.16.10"], cwd=git_directory)
    empty_commit(git_directory, "Change 1 (#1)")
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=git_directory, text=True
    ).strip()
    umbrella = github_api.pull_request(10, labels=("breaking", "release"))
    github_api.pull_request(1, labels=("breaking",))
    github_api.commit("Change 1 (#1)", umbrella, oid=head)

    release(
        directory=git_directory,
        update_version_files=False,
        only_sections=[],
        without_sections=[],
    )

    assert "Using new version 0.17.0" in capsys.readouterr().out
    changelog = (git_directory / "CHANGELOG.md").read_text()
    assert "## 0.17.0" in changelog
    assert "[#1](https://github.com/owner/repo/pull/1)" in changelog
    assert "[#10]" not in changelog
