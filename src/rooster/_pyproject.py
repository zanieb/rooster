"""
Utilities for interacting with `pyproject.toml` files.
"""
from pathlib import Path

import tomllib
from packaging.version import Version


class PyProjectError(Exception):
    """
    Error when reading a `pyproject.toml` file.
    """

    pass


def update_pyproject_version(path: Path, version: Version) -> None:
    """
    Update the version in a `pyproject.toml` file.
    """
    contents = path.read_text()
    parsed = tomllib.loads(contents)

    # We could consider supporting Poetry projects, but let's stick to the standards for now.
    if "project" not in parsed:
        raise PyProjectError("Missing `project` section.")

    if "version" not in parsed["project"]:
        raise PyProjectError("Missing `project.version` field.")

    old_version = parsed["project"]["version"]
    contents = contents.replace(f'version = "{old_version}"', f'version = "{version}"')
    path.write_text(contents)


def get_pyproject_version(path: Path) -> Version:
    """
    Read the current version from a `pyproject.toml` file.
    """
    contents = path.read_text()
    parsed = tomllib.loads(contents)
    return Version(parsed["project"]["version"])
