"""
Utilities for working with version numbers.
"""

from enum import Enum
from pathlib import Path
from typing import Any

import pygit2 as git
import tomllib
from packaging.version import InvalidVersion, Version

from rooster._config import BumpType, Config, VersionFile
from rooster._git import get_tags

CARGO_PRE_MAP = {"a": "alpha", "b": "beta", "rc": "rc"}


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
    pre = None

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
        case BumpType.pre:
            if not version.is_prerelease:
                pre = "a1"
            else:
                pre = f"{version.pre[0]}{version.pre[1] + 1}"
        case _:
            raise ValueError(f"Invalid bump type: {bump_type}")

    # Build a new  version string (`Version` is immutable)
    parts = []
    if version.epoch != 0:
        parts.append(f"{version.epoch}!")

    # Update release segment
    parts.append(".".join(str(x) for x in release))

    if pre:
        parts.append(pre)

    return Version("".join(parts))


def to_cargo_version(version: Version) -> str:
    """
    Convert a version to a string suitable for Cargo.toml.
    """
    if not version.is_prerelease:
        return f"{version.major}.{version.minor}.{version.micro}"
    return f"{version.major}.{version.minor}.{version.micro}-{CARGO_PRE_MAP[version.pre[0]]}.{version.pre[1]}"


def update_version_file(
    version_file: Path | VersionFile, old_version: Version, new_version: Version
) -> None:
    if isinstance(version_file, Path):
        path = version_file
        format = None
        field = None
    else:
        path = version_file.path
        format = version_file.format
        field = version_file.field

    if format == "cargo" or path.name.lower() == "cargo.toml":
        update_toml_version(
            path,
            field or "package.version",
            to_cargo_version(old_version),
            to_cargo_version(new_version),
        )
    elif format == "pyproject" or path.name.lower() == "pyproject.toml":
        update_toml_version(
            path, field or "project.version", str(old_version), str(new_version)
        )
    elif path.suffix.lower() == ".md" or path.suffix.lower() == ".txt":
        if old_version is None:
            raise ValueError(
                f"Cannot update version in file {path.name} without a previous version"
            )
        update_text_version(path, str(old_version), str(new_version))
    else:
        raise ValueError(
            f"Unsupported version update file {path.name}; expected 'Cargo.toml', 'pyproject.toml', '*.txt', or '*.md' file"
        )


def update_text_version(path: Path, old_version: str, new_version: str) -> None:
    """
    Update the version in a basic text file.
    """
    contents = path.read_text()
    path.write_text(contents.replace(old_version, new_version))


def update_toml_version(
    path: Path,
    key: str,
    old_version: str,
    new_version: str,
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

    last_key = key.split(".")[-1]

    # Ensure the contents matches the expected old version
    if found_old_version != old_version:
        raise ValueError(
            f"Mismatched version in {path}::{key}; expected {old_version} found {found_old_version}"
        )

    # Update with a string replacement to avoid reformatting the whole file
    contents = contents.replace(
        f'{last_key} = "{old_version}"', f'{last_key} = "{new_version}"', 1
    )

    # Confirm we updated the correct key
    new_parsed = tomllib.loads(contents)
    found_new_version = _get_nested_key(new_parsed, key)
    if found_new_version != new_version:
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
