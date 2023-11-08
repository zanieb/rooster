from __future__ import annotations

from pathlib import Path

import pydantic
import tomllib
from typing_extensions import Self


class Config(pydantic.BaseModel):
    """
    Configuration options and defaults for Rooster.
    """

    major_labels: frozenset[str] = frozenset(["breaking"])
    minor_labels: frozenset[str] = frozenset(["feature"])
    patch_labels: frozenset[str] = frozenset(["fix"])

    changelog_contributors: bool = True
    changelog_sections: dict[str, str] = {
        "breaking": "Breaking changes",
        "feature": "New features",
        "fix": "Bug fixes",
    }
    changelog_ignore_labels: frozenset[str] = frozenset([])
    changelog_ignore_authors: frozenset[str] = frozenset(["dependabot"])

    change_template: (
        str
    ) = "- {pull_request.title} ([#{pull_request.number}]({pull_request.url}))"

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
