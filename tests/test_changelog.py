from datetime import date

import pytest
from packaging.version import Version

from rooster._changelog import (
    Changelog,
    Document,
    VersionSection,
    entry_to_standalone,
    extract_entry,
    get_versions_from_changelog,
)
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


@pytest.mark.parametrize("level", [1, 2, 3, 4, 5])
def test_generated_sections_are_nested_under_the_release_heading(level):
    document = Document.from_markdown(render_entry([pull_request(1)], level=level))
    release = VersionSection.from_elements(document, document.document.children, level)[
        0
    ]
    sections = release.sections()
    assert [section.title for section in sections] == ["Changes", "Contributors"]
    assert [section.element.level for section in sections] == [level + 1, level + 1]


@pytest.mark.parametrize("level", [0, 6])
def test_invalid_release_heading_levels_are_rejected(level):
    with pytest.raises(ValueError, match="heading level"):
        render_entry([pull_request(1)], level=level)


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


def test_older_release_is_inserted_after_the_complete_previous_section():
    changelog = Changelog.from_markdown(
        "# Changelog\n\n## 2.0.0\n\nNewer release.\n\n- Final newer change\n"
    )
    section = VersionSection.from_elements(
        changelog,
        Document.from_markdown("## 1.0.0\n\nOlder release.\n").document.children,
        2,
    )[0]

    changelog.insert_version_section(section)

    result = changelog.to_markdown()
    assert result.index("Final newer change") < result.index("## 1.0.0")
    assert result.index("## 1.0.0") < result.index("Older release")


@pytest.mark.parametrize("existing", ["1.0.0", "2.0.0"])
def test_insertion_preserves_document_sections_after_versions(existing):
    changelog = Changelog.from_markdown(
        f"# Changelog\n\n## {existing}\n\nOld notes.\n\n# Appendix\n\nKeep this.\n"
    )
    section = VersionSection.from_elements(
        changelog,
        Document.from_markdown("## 1.0.0\n\nNew notes.\n").document.children,
        2,
    )[0]

    changelog.insert_version_section(section)

    result = changelog.to_markdown()
    assert result.index("New notes") < result.index("# Appendix")
    assert "Keep this." in result


def test_unreleased_heading_stays_above_inserted_release():
    changelog = Changelog.from_markdown(
        "# Changelog\n\n## Unreleased\n\nPending.\n\n## 1.0.0\n\nOld notes.\n"
    )
    section = VersionSection.from_elements(
        changelog,
        Document.from_markdown("## 2.0.0\n\nNew notes.\n").document.children,
        2,
    )[0]

    changelog.insert_version_section(section)

    result = changelog.to_markdown()
    assert (
        result.index("Pending.") < result.index("## 2.0.0") < result.index("## 1.0.0")
    )


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_extract_entry_uses_source_boundaries(newline):
    entry = "## 2.0.0\nNotes.\n\n### Fixes\n\n- A fix\n\n".replace("\n", newline)
    changelog = "# Changelog\n\n" + entry + "## 1.0.0\n\nOlder notes.\n"
    assert extract_entry(Config(), changelog, Version("2.0.0")) == entry
    assert extract_entry(Config(), changelog, Version("3.0.0")) is None


@pytest.mark.parametrize("fence", ["```", "~~~~"])
def test_version_headings_in_fenced_examples_are_ignored(fence):
    entry = f"## 1.0.0\n\n{fence}markdown\n## 9.0.0\n{fence}\n\nMore notes.\n\n"
    changelog = entry + "# Appendix\n\nOutside the release.\n"
    assert extract_entry(Config(), changelog, Version("1.0.0")) == entry
    assert get_versions_from_changelog(Config(), changelog) == [Version("1.0.0")]


@pytest.mark.parametrize(
    ("heading", "version"),
    [("## 1.0.0", "1.0.0"), ("## 1.0.0-alpha.1", "1.0.0a1")],
)
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_standalone_entry_replaces_only_the_release_heading(heading, version, newline):
    body = f"{newline}Notes.{newline}{newline}```markdown{newline}{heading}{newline}```{newline}"
    result = entry_to_standalone(heading + newline + body, Version(version))
    assert result == (
        f"## Changes{newline}<!-- Generated from the CHANGELOG file -->{newline}" + body
    )


def test_standalone_entry_accepts_a_heading_without_final_newline():
    assert entry_to_standalone("## 1.0.0", Version("1.0.0")) == (
        "## Changes\n<!-- Generated from the CHANGELOG file -->\n"
    )


def test_extract_cargo_prerelease_with_closing_heading_markers():
    entry = "## 1.0.0-alpha.1 ##\n\nNotes.\n\n"
    assert (
        extract_entry(
            Config(version_format="cargo"), entry + "## 0.9.0\n", Version("1.0.0a1")
        )
        == entry
    )
