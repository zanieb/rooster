"""
Utilities for testing
"""

import subprocess
from pathlib import Path
from typing import Generator

import pytest


@pytest.fixture
def git_directory(tmp_path: Path) -> Path:
    subprocess.check_call(["git", "init", "-b", "main"], cwd=tmp_path)
    subprocess.check_call(
        ["git", "config", "user.email", "test@example.com"], cwd=tmp_path
    )
    subprocess.check_call(["git", "config", "user.name", "Test User"], cwd=tmp_path)
    yield tmp_path


def create_tags(directory: Path, tags: list[str]) -> Generator[str, None, None]:
    """
    Create git tags in the given directory.

    Yields before each tag is created to allow for commits to be made.
    """
    for tag in tags:
        yield tag
        subprocess.check_call(["git", "tag", tag], cwd=directory)


def empty_commit(directory: Path, message: str) -> None:
    """
    Create an empty commit in the given directory.
    """
    subprocess.check_call(
        ["git", "commit", "-m", message, "--allow-empty"], cwd=directory
    )


@pytest.fixture
def mock_pyproject(git_directory: Path) -> Path:
    """
    Creates a mock pyproject.toml file.
    """
    pyproject = git_directory.joinpath("pyproject.toml")
    pyproject.write_text(
        """
        [project]
        name = "test-project"
        version = "0.0.0"
        """
    )
    yield pyproject


@pytest.fixture
def mock_project(git_directory: Path, mock_pyproject: Path) -> Path:
    """
    A basic mock project.
    """
    commit_number = 0
    for i, tag in enumerate(create_tags(git_directory, ["0.1.0", "0.2.0", "0.3.0"])):
        # Generate commits for each tag, increasing the number of commits by one per release
        for inner in range(i + 1):
            commit_number += 1
            empty_commit(
                git_directory, f"Commit {commit_number} should belong to {tag}"
            )

    # Create a bad tag that should be ignored
    create_tags(git_directory, ["foo"])

    empty_commit(git_directory, "Commit {commit_number} should be for the next release")
    commit_number += 1
    empty_commit(git_directory, "Commit {commit_number} should be for the next release")
    yield git_directory


def rooster_command(command: list[str], working_directory: Path | None = None) -> dict:
    process = subprocess.run(
        ["rooster"] + command,
        cwd=working_directory,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return {
        "exit_code": process.returncode,
        "stdout": process.stdout.decode(),
        "stderr": process.stderr.decode(),
    }
