from datetime import date

import pytest
from packaging.version import Version

from rooster._changelog import Document, VersionSection
from rooster._config import Config
from rooster._github import PullRequest


def pull_request(number, *, author="author", labels=()):
    return PullRequest(
        f"Change {number}",
        number,
        frozenset(labels),
        author,
        "repo",
        "owner",
        f"https://github.com/owner/repo/pull/{number}",
    )


def render_entry(
    pull_requests, *, config=None, only_sections=(), without_sections=(), level=2
):
    section = VersionSection.from_pull_requests(
        document=Document.empty(),
        config=config or Config(),
        version=Version("1.0.0"),
        pull_requests=pull_requests,
        only_sections=only_sections,
        without_sections=without_sections,
        level=level,
        release_date=date(2026, 10, 1),
    )
    return section.as_document().to_markdown()


def test_changelog_accepts_pull_request_generators():
    result = render_entry(pull_request(i) for i in [1, 2])

    assert "Change 1" in result
    assert "Change 2" in result
    assert "[@author]" in result


@pytest.mark.parametrize("excluded", ["Features", "feature"])
def test_sections_can_be_excluded_by_name_or_legacy_label(excluded):
    result = render_entry(
        [pull_request(1, labels=["feature"]), pull_request(2)],
        config=Config(section_labels={"Features": ["feature"]}),
        without_sections=[excluded],
    )
    assert "Change 1" not in result
    assert "Change 2" in result


@pytest.mark.parametrize(
    ("config", "section"),
    [
        (Config(), "Changes"),
        (Config(section_labels={"Uncategorized": ["__unknown__"]}), "Uncategorized"),
    ],
)
def test_fallback_section_can_be_selected(config, section):
    result = render_entry([pull_request(1)], config=config, only_sections=[section])
    assert "Change 1" in result


def test_section_filter_does_not_change_label_precedence():
    result = render_entry(
        [pull_request(1, labels=["breaking", "feature"])],
        config=Config(
            section_labels={"Breaking": ["breaking"], "Features": ["feature"]}
        ),
        only_sections=["Features"],
    )
    assert "Change 1" not in result


def test_contributors_are_sorted_and_follow_visible_changes():
    result = render_entry(
        [
            pull_request(1, author="zoe"),
            pull_request(2, author="Bob"),
            pull_request(3, author="alice"),
            pull_request(4, author="ignored", labels=["internal"]),
            pull_request(5, author="hidden", labels=["feature"]),
            pull_request(6, author="bot"),
            pull_request(7, author="alice"),
        ],
        config=Config(
            section_labels={"Features": ["feature"]},
            changelog_ignore_labels=frozenset(["internal"]),
            changelog_ignore_authors=frozenset(["bot"]),
        ),
        without_sections=["Features"],
    )
    contributors = result.split("### Contributors\n", 1)[1]
    assert contributors.strip().splitlines() == [
        "- [@alice](https://github.com/alice)",
        "- [@Bob](https://github.com/Bob)",
        "- [@zoe](https://github.com/zoe)",
    ]
