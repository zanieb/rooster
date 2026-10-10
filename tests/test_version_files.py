import pytest
from packaging.version import Version

from rooster._config import VersionFile
from rooster._versions import update_version_file


@pytest.mark.parametrize(
    ("name", "format", "field", "contents", "expected"),
    [
        ("VERSION", "text", None, "1.2.3\n", "1.2.4\n"),
        (
            "release.toml",
            "toml",
            "app.version",
            '[app]\nversion = "1.2.3"\n',
            '[app]\nversion = "1.2.4"\n',
        ),
        (
            "release.toml",
            "cargo",
            None,
            '[package]\nversion = "1.2.3"\n',
            '[package]\nversion = "1.2.4"\n',
        ),
        (
            "project.toml",
            "pyproject",
            None,
            '[project]\nversion = "1.2.3"\n',
            '[project]\nversion = "1.2.4"\n',
        ),
        ("pyproject.toml", "text", None, "release: 1.2.3\n", "release: 1.2.4\n"),
        (
            "pyproject.toml",
            None,
            None,
            '[project]\nversion = "1.2.3"\n',
            '[project]\nversion = "1.2.4"\n',
        ),
    ],
)
def test_explicit_version_file_formats(
    tmp_path, name, format, field, contents, expected
):
    path = tmp_path / name
    path.write_text(contents)

    update_version_file(
        VersionFile(path=path, format=format, field=field),
        Version("1.2.3"),
        Version("1.2.4"),
    )

    assert path.read_text() == expected
