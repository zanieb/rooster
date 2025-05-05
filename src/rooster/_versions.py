"""
Utilities for working with version numbers.
"""

from enum import Enum
from pathlib import Path
from typing import Any

import pygit2 as git
import tomllib
from packaging.version import InvalidVersion, Version

from rooster._config import Config
from rooster._git import get_tags
from rooster._pyproject import update_pyproject_version


class BumpType(Enum):
    major = "major"
    minor = "minor"
    patch = "patch"


def versions_from_git_tags(
    config: Config, repo: git.repository.Repository
) -> list[Version]:
    """
    Get versions of the project from git tags.
    """
    tags = get_tags(config, repo)
    versions = parse_versions(tags)
    return versions


def parse_versions(version_strings: list[str]) -> list[Version]:
    """
    Parse version strings typed, validated objects.

    Invalid versions will be silently ignored.
    """
    versions = []
    for version in version_strings:
        try:
            versions.append(Version(version))
        except InvalidVersion:
            # Ignore tags that are not valid versions
            pass
    return list(sorted(versions))


def get_latest_version(versions: list[Version]) -> Version | None:
    """
    Get the newest version from a collection of versions.
    """
    if not versions:
        return None
    return sorted(versions, reverse=True)[0]


def get_previous_version(versions: list[Version], version: Version) -> Version | None:
    """
    Get the version preceding a given version from a collection of versions.
    """
    if version not in versions:
        # Ensure the given version is included (but do not modify the given list)
        versions = [version] + versions
    versions = sorted(versions)
    index = versions.index(version) - 1
    if index < 0:
        return None
    return versions[index]


def bump_version(version: Version, bump_type: BumpType) -> Version:
    """
    Create a new version from a preceding one, increasing the given component.
    """
    # Pull the release section from the version and increment the appropriate number
    release = list(version.release)

    match bump_type:
        case BumpType.patch:
            release[2] += 1
        case BumpType.minor:
            release[1] += 1
            release[2] = 0
        case BumpType.major:
            release[0] += 1
            # Reset minor and patch versions
            release[1] = 0
            release[2] = 0
        case _:
            raise ValueError(f"Invalid bump type: {bump_type}")

    # Build a new  version string (`Version` is immutable)
    parts = []
    if version.epoch != 0:
        parts.append(f"{version.epoch}!")

    # Update release segment
    parts.append(".".join(str(x) for x in release))

    # We do not include other sections like dev/local/post since we are publishing
    # a new version. We could allow doing so in a separate function but then we
    # would need to construct the object again.
    return Version("".join(parts))


def update_file_version(path: Path, old_version: Version, new_version: Version) -> None:
    if path.name.lower() == "cargo.toml":
        update_toml_version(path, "package.version", old_version, new_version)
    elif path.name.lower() == "pyproject.toml":
        update_pyproject_version(path, new_version)
    elif path.name.lower().endswith(".md") or path.name.lower().endswith(".txt"):
        update_text_version(path, old_version, new_version)
    else:
        raise ValueError(
            f"Unsupported version update file {path.name}; expected 'Cargo.toml', 'pyproject.toml', '*.txt', or '*.md' file"
        )


def update_text_version(path: Path, old_version: Version, new_version: Version) -> None:
    """
    Update the version in a basic text file.
    """
    contents = path.read_text()
    path.write_text(contents.replace(str(old_version), str(new_version)))


def update_toml_version(
    path: Path, key: str, old_version: Version, new_version: Version
) -> None:
    """
    Update the version in a toml file.
    """
    contents = path.read_text()
    parsed = tomllib.loads(contents)

    # First check for the key to avoid replacing the wrong thing
    try:
        found_old_version = _get_nested_key(parsed, key)
    except KeyError:
        raise KeyError(f"{key} not found in {path}")

    # Ensure the contents matches the expected old version
    if Version(found_old_version) != old_version:
        raise Version(
            f"Mismatched version in {path}::{key}; expected {old_version} found {found_old_version}"
        )

    # Update with a string replacement to avoid reformatting the whole file
    contents = contents.replace(
        f'version = "{old_version}"', f'version = "{new_version}"', 1
    )

    # Confirm we updated the correct key
    new_parsed = tomllib.loads(contents)
    found_new_version = _get_nested_key(new_parsed, key)
    if found_new_version != str(new_version):
        raise RuntimeError(
            f"Failed safety check when updating version at {path}::{key}; expected {new_version} found {found_new_version}"
        )

    # Write the update
    path.write_text(contents)


def _get_nested_key(source: dict[str, Any], key: str):
    current = source
    for name in key.split("."):
        current = current[name]

    return current
