from datetime import date

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
