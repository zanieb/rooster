from pathlib import Path

import pydantic
import tomllib


class Config(pydantic.BaseModel):
    major_labels: frozenset[str] = frozenset(["breaking"])
    minor_labels: frozenset[str] = frozenset(["feature"])
    patch_labels: frozenset[str] = frozenset(["fix"])

    changelog_sections: dict[str, str] = {
        "breaking": "Breaking changes",
        "feature": "New features",
        "fix": "Bug fixes",
    }
    changelog_ignore_labels: frozenset[str] = frozenset([])
    changelog_ignore_authors: frozenset[str] = frozenset(["dependabot"])

    change_template: str = "- {pull_request.title} (#{pull_request.number})"

    @pydantic.validator("changelog_sections", always=True)
    def require_unknown_key(cls, value):
        value.setdefault("__unknown__", "Other changes")
        return value


def get_config(repo: Path) -> Config:
    pyproject_path = repo / "pyproject.toml"
    if not pyproject_path.exists():
        return Config()
    pyproject = tomllib.loads(pyproject_path.read_text())
    section = pyproject.get("tool", {}).get("rooster", {})
    return Config(**section)
