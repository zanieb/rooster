import pytest
from packaging.version import Version

from rooster._changelog import get_versions_from_changelog
from rooster._config import BumpType, Config
from rooster._git import get_commit_for_tag, repo_from_path
from rooster._testing import git_directory
from rooster._versions import (
    bump_version,
    get_latest_version,
    parse_version,
    to_cargo_version,
    versions_from_git_tags,
)
from tests.test_git import commit, git


@pytest.mark.parametrize("prefix", ["v", "release/", ""])
@pytest.mark.parametrize("annotated", [False, True])
def test_version_tags_retain_their_lookup_name(git_directory, prefix, annotated):
    head = commit(git_directory, "Release")
    tag = prefix + "1.2.3"
    args = ["tag", tag]
    if annotated:
        args.extend(["-a", "-m", "Release"])
    git(git_directory, *args)
    repo = repo_from_path(git_directory)

    tags = versions_from_git_tags(Config(version_tag_prefix=prefix), repo)

    assert tags == {Version("1.2.3"): tag}
    assert get_commit_for_tag(repo, tags[Version("1.2.3")]).id == head.id


def test_latest_version_accepts_iterators():
    assert get_latest_version(iter([Version("1.0"), Version("2.0")])) == Version("2.0")
    assert get_latest_version(iter([])) is None


def test_version_tags_ignore_releases_on_other_branches(git_directory):
    commit(git_directory, "Shared release")
    git(git_directory, "tag", "1.0.0")
    git(git_directory, "switch", "-c", "next")
    commit(git_directory, "Future release")
    git(git_directory, "tag", "2.0.0")
    git(git_directory, "switch", "main")
    commit(git_directory, "Maintenance release")
    git(git_directory, "tag", "1.0.1")

    assert versions_from_git_tags(Config(), repo_from_path(git_directory)) == {
        Version("1.0.0"): "1.0.0",
        Version("1.0.1"): "1.0.1",
    }


def test_changelog_versions_can_be_traversed_repeatedly():
    versions = get_versions_from_changelog(
        Config(), "## 2.0.0\n## unreleased\n## 1.0.0\n"
    )
    assert list(versions) == [Version("2.0.0"), Version("1.0.0")]
    assert list(versions) == [Version("2.0.0"), Version("1.0.0")]


def test_development_version_can_start_an_alpha_release():
    assert bump_version(Version("1.0.0.dev1"), BumpType.pre) == Version("1.0.0a1")


@pytest.mark.parametrize(
    ("version", "bump", "expected"),
    [
        ("1", BumpType.major, "2.0.0"),
        ("1", BumpType.minor, "1.1.0"),
        ("1", BumpType.patch, "1.0.1"),
        ("1.2", BumpType.major, "2.0.0"),
        ("1.2", BumpType.minor, "1.3.0"),
        ("1.2", BumpType.patch, "1.2.1"),
        ("1.2", BumpType.pre, "1.2a1"),
        ("2!1.2", BumpType.patch, "2!1.2.1"),
    ],
)
def test_bump_short_release_versions(version, bump, expected):
    assert str(bump_version(Version(version), bump)) == expected


def test_cargo_conversion_does_not_drop_development_suffix():
    with pytest.raises(ValueError, match="Development releases"):
        to_cargo_version(Version("1.0.0.dev1"))


@pytest.mark.parametrize(
    ("version", "expected"),
    [("1.0.0", "1.0.0"), ("1.0.0a1", "1.0.0-alpha.1"), ("1.0.0rc2", "1.0.0-rc.2")],
)
def test_cargo_version_conversion(version, expected):
    assert to_cargo_version(Version(version)) == expected


@pytest.mark.parametrize(
    "tag",
    [
        "not-a-version",
        "1.2.3-preview.1",
        "1.2.3-alpha",
        "1.2.3-alpha.nope",
        "1.2.3-alpha.1.extra",
        "1.2.3-rc.1-ignored",
        "1.2",
        "01.2.3",
        "1!1.2.3",
        "1.2.3rc1",
    ],
)
def test_unsupported_cargo_tags_are_ignored(tag):
    assert parse_version(Config(version_format="cargo"), tag) is None


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("1.2.3", "1.2.3"),
        ("1.2.3-alpha.0", "1.2.3a0"),
        ("1.2.3-beta.2", "1.2.3b2"),
        ("1.2.3-rc.1", "1.2.3rc1"),
        ("1.2.3+build.42", "1.2.3+build.42"),
        ("1.2.3-rc.1+build.42", "1.2.3rc1+build.42"),
    ],
)
def test_supported_cargo_tags(tag, expected):
    assert parse_version(Config(version_format="cargo"), tag) == Version(expected)
