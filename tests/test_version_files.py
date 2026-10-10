import pytest
from packaging.version import Version

from rooster._config import VersionFile
from rooster._versions import update_toml_version, update_version_file


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


@pytest.mark.parametrize(
    ("contents", "expected"),
    [
        (
            "[project]\nversion='1.2.3' # release\n",
            "[project]\nversion='1.2.4' # release\n",
        ),
        ('[project]\nversion  =  "1.2.3"\n', '[project]\nversion  =  "1.2.4"\n'),
        (
            'project = {version = "1.2.3", name = "example"}\n',
            'project = {version = "1.2.4", name = "example"}\n',
        ),
        ('project.version = "1.2.3"\n', 'project.version = "1.2.4"\n'),
        ('[project]\n"version" = "1.2.3"\n', '[project]\n"version" = "1.2.4"\n'),
        (
            '# version = "1.2.3"\n[other]\nversion = "1.2.3"\n[project]\nversion = "1.2.3"\n',
            '# version = "1.2.3"\n[other]\nversion = "1.2.3"\n[project]\nversion = "1.2.4"\n',
        ),
    ],
)
def test_toml_update_changes_only_the_selected_field(tmp_path, contents, expected):
    path = tmp_path / "pyproject.toml"
    path.write_text(contents)

    update_toml_version(path, "project.version", "1.2.3", "1.2.4")

    assert path.read_text() == expected


@pytest.mark.parametrize("key", ["project.version", "project.missing"])
def test_toml_update_leaves_invalid_inputs_unchanged(tmp_path, key):
    path = tmp_path / "pyproject.toml"
    contents = '[project]\nversion = "0.9.0"\n'
    path.write_text(contents)

    with pytest.raises((KeyError, ValueError)):
        update_toml_version(path, key, "1.2.3", "1.2.4")

    assert path.read_text() == contents
