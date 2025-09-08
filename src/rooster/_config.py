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

    require_labels: list[str | SubmoduleLabels] = list()
    ignore_labels: list[str | SubmoduleLabels] = list()
    section_labels: dict[str, list[str]] = {}
    version_format: Literal["pep440", "cargo"] = "pep440"
    submodules: list[Path] = []

    changelog_file: str = "CHANGELOG.md"
    changelog_contributors: bool = True
    changelog_sections: dict[str, str] = {}
    changelog_ignore_labels: frozenset[str] = frozenset([])
    changelog_ignore_authors: frozenset[str] = frozenset(["dependabot"])

    change_template: str = (
        "- {pull_request.title} ([#{pull_request.number}]({pull_request.url}))"
    )
    trim_title_prefixes: frozenset[str] = frozenset()

    # Paths to files to replace versions at
    version_files: list[Path | VersionFile | SubstitutionEntry] = [
        Path("pyproject.toml")
    ]

    # The default version bump to use
    default_bump_type: BumpType = BumpType.patch

    # A prefix to identify tags as versions e.g. "v"
    version_tag_prefix: str = ""

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

    def required_labels_for_submodule(self, path: Path) -> frozenset[str]:
        for item in self.require_labels:
            if isinstance(item, SubmoduleLabels) and item.submodule == path.name:
                return item.labels

    def ignored_labels_for_submodule(self, path: Path) -> frozenset[str]:
        for item in self.ignore_labels:
            if isinstance(item, SubmoduleLabels) and item.submodule == path.name:
                return item.labels

    def global_required_labels(self) -> frozenset[str]:
        return frozenset(item for item in self.require_labels if isinstance(item, str))

    def global_ignored_labels(self) -> frozenset[str]:
        return frozenset(
            item for item in self.ignore_labels if isinstance(item, str)
        ).union(set(self.changelog_ignore_labels))


class VersionFile(pydantic.BaseModel):
    path: Path
    format: Literal["toml", "text", "cargo"] = "text"
    field: str | None = None

    def __str__(self):
        return str(self.path)


class SubstitutionEntry(pydantic.BaseModel):
    target: str
    replace: str | None = None

    def __str__(self):
        return str(self.target)


class SubmoduleLabels(pydantic.BaseModel):
    submodule: str
    labels: frozenset[str] = frozenset()
