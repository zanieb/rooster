from rooster._testing import (
    git_directory,
    create_tags,
    empty_commit,
    mock_project,
    rooster_command,
)

from pathlib import Path
import subprocess
import io


def test_entry_no_remote(mock_project: Path, snapshot):
    assert (
        rooster_command(["entry", str(mock_project.resolve()), "--version", "0.1.0"])
        == snapshot
    )
