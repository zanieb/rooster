import io
import subprocess
from pathlib import Path

from rooster._pyproject import update_pyproject_version
from rooster._testing import (
    create_tags,
    empty_commit,
    git_directory,
    mock_project,
    mock_pyproject,
    rooster_command,
)


def test_changelog_no_version_no_pyproject(mock_project: Path, snapshot):
    (mock_project / "pyproject.toml").unlink()
    assert rooster_command(["changelog", str(mock_project.resolve())]) == snapshot


def test_changelog_no_version(mock_project: Path, mock_pyproject: Path, snapshot):
    # Should use version from pyproject file
    update_pyproject_version(mock_pyproject, "0.2.0")
    assert rooster_command(["changelog", str(mock_project.resolve())]) == snapshot


def test_changelog_no_remote(mock_project: Path, snapshot):
    assert (
        rooster_command(
            ["changelog", str(mock_project.resolve()), "--version", "0.1.0"]
        )
        == snapshot
    )
