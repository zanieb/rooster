from __future__ import annotations

from enum import StrEnum, auto
from pathlib import Path
from typing import Literal

import pydantic
import tomllib
from typing_extensions import Self


class BumpType(StrEnum):
    major = auto()
    minor = auto()
    patch = auto()
    pre = auto()


def to_kebab(string: str) -> str:
    """Convert a snake_case string to kebab-case."""
    return string.replace("_", "-")


class Config(pydantic.BaseModel):
    """
    Configuration options and defaults for Rooster.
    """

    major_labels: frozenset[str] = frozenset(["breaking"])
    minor_labels: frozenset[str] = frozenset(["feature"])
    patch_labels: frozenset[str] = frozenset(["fix"])

    required_labels: frozenset[str] = frozenset()
    version_format: Literal["pep440", "cargo"] = "pep440"

    changelog_file: str = "CHANGELOG.md"
    changelog_contributors: bool = True
    changelog_sections: dict[str, str] = {
        "breaking": "Breaking changes",
        "feature": "New features",
        "fix": "Bug fixes",
    }
    changelog_ignore_labels: frozenset[str] = frozenset([])
    changelog_ignore_authors: frozenset[str] = frozenset(["dependabot"])

    change_template: str = (
        "- {pull_request.title} ([#{pull_request.number}]({pull_request.url}))"
    )

    # Paths to files to replace versions at
    version_files: list[Path | VersionFile] = [Path("pyproject.toml")]

    # The default version bump to use
    default_bump_type: BumpType = BumpType.patch

    # A prefix to identify tags as versions e.g. "v"
    version_tag_prefix: str = ""

    @pydantic.validator("changelog_sections", always=True)
    def require_unknown_key(cls, value):
        value.setdefault("__unknown__", "Other changes")
        return value

    @classmethod
    def from_directory(cls: type[Self], dirpath: Path) -> Self:
        """
        Load the configuration from a `pyproject.toml` file in a directory.

        If there is no `pyproject.toml` file present, the default config will be returned.
        """
        path = dirpath / "pyproject.toml"
        if not path.exists():
            return cls()
        return cls.from_path(path)

    @classmethod
    def from_path(cls: type[Self], path: Path) -> Self:
        """
        Load the configuration from a `pyproject.toml` file.

        If the file does not exist, an error will be raised.
        """
        pyproject = tomllib.loads(path.read_text())
        section = pyproject.get("tool", {}).get("rooster", {})
        return cls(**section)

    model_config = pydantic.ConfigDict(alias_generator=to_kebab, populate_by_name=True)


class VersionFile(pydantic.BaseModel):
    path: Path
    format: Literal["toml", "text", "cargo"] = "text"
    field: str | None = None

    def __str__(self):
        return str(self.path)
