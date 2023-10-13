from rooster._testing import (
    git_directory,
    create_tags,
    empty_commit,
    mock_project,
    rooster_command,
    mock_pyproject,
)
from rooster._pyproject import update_pyproject_version

from pathlib import Path
import subprocess
import io


def test_entry_no_version_no_pyproject(mock_project: Path, snapshot):
    (mock_project / "pyproject.toml").unlink()
    assert rooster_command(["entry", str(mock_project.resolve())]) == snapshot


def test_entry_no_version(mock_project: Path, mock_pyproject: Path, snapshot):
    # Should use version from pyproject file
    update_pyproject_version(mock_pyproject, "0.2.0")
    assert rooster_command(["entry", str(mock_project.resolve())]) == snapshot


def test_entry_no_remote(mock_project: Path, snapshot):
    assert (
        rooster_command(["entry", str(mock_project.resolve()), "--version", "0.1.0"])
        == snapshot
    )
