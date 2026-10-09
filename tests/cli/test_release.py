import subprocess

from rooster._cli import release
from rooster._testing import empty_commit, git_directory


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
