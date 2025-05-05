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


def get_pyproject_version(path: Path) -> Version:
    """
    Read the current version from a `pyproject.toml` file.
    """
    contents = path.read_text()
    parsed = tomllib.loads(contents)
    return Version(parsed["project"]["version"])
