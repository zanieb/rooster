import io
import subprocess
from pathlib import Path

from inline_snapshot import Is, snapshot

from rooster._pyproject import update_pyproject_version
from rooster._testing import (
    create_tags,
    empty_commit,
    git_directory,
    mock_project,
    mock_pyproject,
    rooster_command,
)


def test_release_no_remote(mock_project: Path, mock_pyproject: Path):
    assert rooster_command(["release", str(mock_project.resolve())]) == snapshot(
        {
            "exit_code": 1,
            "stdout": """\
Found last version tag 0.3.0 at e65bb424.
Collecting commits between e65bb424 (0.3.0) and 2252bc5c (HEAD)...
Found 3 commits since last release.
Failed to determine remote for repository.
""",
            "stderr": "",
        }
    )
