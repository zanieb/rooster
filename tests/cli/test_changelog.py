from pathlib import Path

from inline_snapshot import snapshot
from packaging.version import Version

from rooster._cli import update_changelog
from rooster._config import Config
from rooster._github import PullRequest


def test_update_changelog(tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    update_changelog(
        changelog,
        Version("0.1.0"),
        config=Config(),
        pull_requests=[
            PullRequest(
                title="Test",
                number=1,
                labels=frozenset(),
                author="author",
                repo_name="repo",
                repo_owner="owner",
            )
        ],
    )
    assert changelog.read_text() == snapshot("""\
# Changelog

## 0.1.0

### Other changes

- Test ([#1](https://github.com/owner/repo/pull/1))

### Contributors

- [@author](https://github.com/author)


""")

    update_changelog(
        changelog,
        Version("0.1.0"),
        config=Config(),
        pull_requests=[
            PullRequest(
                title="Test",
                number=1,
                labels=frozenset(),
                author="author",
                repo_name="repo",
                repo_owner="owner",
            ),
            PullRequest(
                title="Another test",
                number=2,
                labels=frozenset(),
                author="author",
                repo_name="repo",
                repo_owner="owner",
            ),
        ],
    )
    assert changelog.read_text() == snapshot("""\
# Changelog

## 0.1.0

### Other changes

- Another test ([#2](https://github.com/owner/repo/pull/2))
- Test ([#1](https://github.com/owner/repo/pull/1))

### Contributors

- [@author](https://github.com/author)

""")

    update_changelog(
        changelog,
        Version("0.2.0"),
        config=Config(),
        pull_requests=[
            PullRequest(
                title="Test",
                number=3,
                labels=frozenset(),
                author="author",
                repo_name="repo",
                repo_owner="owner",
            ),
            PullRequest(
                title="Another test",
                number=4,
                labels=frozenset(),
                author="author",
                repo_name="repo",
                repo_owner="owner",
            ),
        ],
    )
    assert changelog.read_text() == snapshot("""\
# Changelog

## 0.2.0

### Other changes

- Another test ([#4](https://github.com/owner/repo/pull/4))
- Test ([#3](https://github.com/owner/repo/pull/3))

### Contributors

- [@author](https://github.com/author)

## 0.1.0

### Other changes

- Another test ([#2](https://github.com/owner/repo/pull/2))
- Test ([#1](https://github.com/owner/repo/pull/1))

### Contributors

- [@author](https://github.com/author)
""")

    update_changelog(
        changelog,
        Version("0.3.0"),
        config=Config(),
        pull_requests=[
            PullRequest(
                title="Test",
                number=6,
                labels=frozenset(),
                author="author",
                repo_name="repo",
                repo_owner="owner",
            ),
            PullRequest(
                title="Another test",
                number=7,
                labels=frozenset(),
                author="author",
                repo_name="repo",
                repo_owner="owner",
            ),
        ],
    )
    assert changelog.read_text() == snapshot("""\
# Changelog

## 0.3.0

### Other changes

- Another test ([#7](https://github.com/owner/repo/pull/7))
- Test ([#6](https://github.com/owner/repo/pull/6))

### Contributors

- [@author](https://github.com/author)

## 0.2.0

### Other changes

- Another test ([#4](https://github.com/owner/repo/pull/4))
- Test ([#3](https://github.com/owner/repo/pull/3))

### Contributors

- [@author](https://github.com/author)

## 0.1.0

### Other changes

- Another test ([#2](https://github.com/owner/repo/pull/2))
- Test ([#1](https://github.com/owner/repo/pull/1))

### Contributors

- [@author](https://github.com/author)
""")

    update_changelog(
        changelog,
        Version("0.2.0"),
        config=Config(),
        pull_requests=[
            PullRequest(
                title="Test",
                number=3,
                labels=frozenset(),
                author="author",
                repo_name="repo",
                repo_owner="owner",
            ),
            PullRequest(
                title="Another test",
                number=4,
                labels=frozenset(),
                author="author",
                repo_name="repo",
                repo_owner="owner",
            ),
            PullRequest(
                title="Another test",
                number=5,
                labels=frozenset(),
                author="author",
                repo_name="repo",
                repo_owner="owner",
            ),
        ],
    )
    assert changelog.read_text() == snapshot("""\
# Changelog

## 0.3.0

### Other changes

- Another test ([#7](https://github.com/owner/repo/pull/7))
- Test ([#6](https://github.com/owner/repo/pull/6))

### Contributors

- [@author](https://github.com/author)

## 0.2.0

### Other changes

- Another test ([#4](https://github.com/owner/repo/pull/4))
- Another test ([#5](https://github.com/owner/repo/pull/5))
- Test ([#3](https://github.com/owner/repo/pull/3))

### Contributors

- [@author](https://github.com/author)

## 0.1.0

### Other changes

- Another test ([#2](https://github.com/owner/repo/pull/2))
- Test ([#1](https://github.com/owner/repo/pull/1))

### Contributors

- [@author](https://github.com/author)
""")


def test_update_changelog_sections(tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    update_changelog(
        changelog,
        Version("0.1.0"),
        config=Config(changelog_sections={"a": "A"}),
        pull_requests=[
            PullRequest(
                title="Test",
                number=1,
                labels=frozenset("a"),
                author="author",
                repo_name="repo",
                repo_owner="owner",
            )
        ],
    )
    assert changelog.read_text() == snapshot("""\
# Changelog

## 0.1.0

### A

- Test ([#1](https://github.com/owner/repo/pull/1))

### Contributors

- [@author](https://github.com/author)


""")

    update_changelog(
        changelog,
        Version("0.1.0"),
        config=Config(changelog_sections={"a": "A", "b": "B"}),
        pull_requests=[
            PullRequest(
                title="Test",
                number=1,
                labels=frozenset("a"),
                author="author",
                repo_name="repo",
                repo_owner="owner",
            ),
            PullRequest(
                title="Another test",
                number=2,
                labels=frozenset("b"),
                author="author",
                repo_name="repo",
                repo_owner="owner",
            ),
        ],
    )
    assert changelog.read_text() == snapshot("""\
# Changelog

## 0.1.0

### A

- Test ([#1](https://github.com/owner/repo/pull/1))

### B

- Another test ([#2](https://github.com/owner/repo/pull/2))

### Contributors

- [@author](https://github.com/author)

""")


def test_update_changelog_without_sections(tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    update_changelog(
        changelog,
        Version("0.1.0"),
        config=Config(changelog_sections={"a": "A", "b": "B"}),
        pull_requests=[
            PullRequest(
                title="Test",
                number=1,
                labels=frozenset("a"),
                author="author",
                repo_name="repo",
                repo_owner="owner",
            ),
            PullRequest(
                title="Another test",
                number=2,
                labels=frozenset("b"),
                author="author",
                repo_name="repo",
                repo_owner="owner",
            ),
        ],
        without_sections={"b"},
    )
    assert changelog.read_text() == snapshot("""\
# Changelog

## 0.1.0

### A

- Test ([#1](https://github.com/owner/repo/pull/1))

### Contributors

- [@author](https://github.com/author)


""")


def test_update_changelog_only_sections(tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    update_changelog(
        changelog,
        Version("0.1.0"),
        config=Config(changelog_sections={"a": "A", "b": "B"}),
        pull_requests=[
            PullRequest(
                title="Test",
                number=1,
                labels=frozenset("a"),
                author="author",
                repo_name="repo",
                repo_owner="owner",
            ),
            PullRequest(
                title="Another test",
                number=2,
                labels=frozenset("b"),
                author="author",
                repo_name="repo",
                repo_owner="owner",
            ),
        ],
        only_sections={"b"},
    )
    assert changelog.read_text() == snapshot("""\
# Changelog

## 0.1.0

### B

- Another test ([#2](https://github.com/owner/repo/pull/2))

### Contributors

- [@author](https://github.com/author)


""")
