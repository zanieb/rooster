import subprocess

from rooster._cli import release
from rooster._testing import empty_commit, git_directory


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
