import pytest
from packaging.version import Version

from rooster._changelog import get_versions_from_changelog
from rooster._config import BumpType, Config
from rooster._versions import bump_version, get_latest_version, to_cargo_version


def test_latest_version_accepts_iterators():
    assert get_latest_version(iter([Version("1.0"), Version("2.0")])) == Version("2.0")
    assert get_latest_version(iter([])) is None


def test_changelog_versions_can_be_traversed_repeatedly():
    versions = get_versions_from_changelog(
        Config(), "## 2.0.0\n## unreleased\n## 1.0.0\n"
    )
    assert list(versions) == [Version("2.0.0"), Version("1.0.0")]
    assert list(versions) == [Version("2.0.0"), Version("1.0.0")]


def test_development_version_can_start_an_alpha_release():
    assert bump_version(Version("1.0.0.dev1"), BumpType.pre) == Version("1.0.0a1")


def test_cargo_conversion_does_not_drop_development_suffix():
    with pytest.raises(ValueError, match="Development releases"):
        to_cargo_version(Version("1.0.0.dev1"))


@pytest.mark.parametrize(
    ("version", "expected"),
    [("1.0.0", "1.0.0"), ("1.0.0a1", "1.0.0-alpha.1"), ("1.0.0rc2", "1.0.0-rc.2")],
)
def test_cargo_version_conversion(version, expected):
    assert to_cargo_version(Version(version)) == expected
