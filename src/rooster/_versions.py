"""
Utilities for working with version numbers.
"""

from enum import Enum
from pathlib import Path

from packaging.version import InvalidVersion, Version

from rooster._git import get_tags


class BumpType(Enum):
    major = "major"
    minor = "minor"
    patch = "patch"


def versions_from_git_tags(repo: Path) -> list[Version]:
    """
    Get versions of the project from git tags.
    """
    tags = get_tags(repo)
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
    return versions


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
