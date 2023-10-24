from pathlib import Path

import tomllib
from packaging.version import Version


def update_pyproject_version(path: Path, version: Version) -> None:
    contents = path.read_text()
    parsed = tomllib.loads(contents)
    old_version = parsed["project"]["version"]
    contents = contents.replace(f'version = "{old_version}"', f'version = "{version}"')
    path.write_text(contents)
