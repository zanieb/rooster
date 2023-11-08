from rooster._config import Config
from rooster._github import PullRequest
from rooster._versions import Version, get_previous_version, parse_versions

VERSION_HEADING_PREFIX = "## "


def generate_changelog(pull_requests: list[PullRequest], config: Config) -> str:
    changelog = ""

    # Initialize the sections dictionary to match the changelog sections config for
    # ordering
    sections = {label: [] for label in config.changelog_sections}

    # De-duplicate pull requests and sort into sections
    for pull_request in set(pull_requests):
        for label in pull_request.labels:
            if label in config.changelog_ignore_labels:
                break
        # Iterate in-order of changelog sections to support user-configured precedence
        for label in config.changelog_sections:
            if label in pull_request.labels:
                sections[label].append(pull_request)
                break
        else:
            sections["__unknown__"].append(pull_request)

    for section, pull_requests in sections.items():
        # Omit empty sections
        if not pull_requests:
            continue

        heading = config.changelog_sections.get(section)
        changelog += f"### {heading}\n"
        for pull_request in pull_requests:
            changelog += config.change_template.format(pull_request=pull_request) + "\n"
        changelog += "\n"

    if config.changelog_contributors:
        changelog += generate_contributors(pull_requests, config)
        changelog += "\n"

    return changelog


def generate_contributors(pull_requests: list[PullRequest], config: Config) -> str:
    contributors = ""
    authors = {
        pull_request.author
        for pull_request in pull_requests
        if pull_request.author not in config.changelog_ignore_authors
    }
    if authors:
        contributors += "### Contributors\n"
        for author in sorted(authors):
            contributors += f"- [@{author}](https://github.com/{author})\n"
    return contributors


def add_or_update_entry(
    version: Version, existing_changelog: str, new_entry: str
) -> str:
    """
    Inject a new entry into the existing changelog, replacing the changelog section
    for the given version or inserting it after the last relevant version.
    """
    new_heading = f"{VERSION_HEADING_PREFIX}{version}\n\n"

    versions = get_versions_from_changelog(existing_changelog)
    previous_version = get_previous_version(versions, version)
    # If there are no versions in the file, just append the entry
    if not previous_version and new_heading not in existing_changelog:
        # print("No versions found in file; appending entry")
        return ensure_spacing(existing_changelog + "\n" + new_heading + new_entry)

    previous_heading = (
        f"{VERSION_HEADING_PREFIX}{previous_version}\n\n" if previous_version else None
    )

    # If the heading exists, replace it with the new entry
    if new_heading in existing_changelog:
        # print("Version found in file; replacing entry")
        start = existing_changelog.index(new_heading)
        end = (
            existing_changelog.index(previous_heading)
            if previous_heading
            else len(existing_changelog)
        )
    else:
        # print("Inserting entry after header")
        start = end = existing_changelog.index(previous_heading)

    # Replace the existing changelog with the new changelog
    new_changelog = (
        existing_changelog[:start]
        + "\n"
        + new_heading
        + new_entry
        + existing_changelog[end:]
        + "\n"
    )

    return ensure_spacing(new_changelog)


def ensure_spacing(changelog: str) -> str:
    # Sloppily ensure we don't have too much spacing
    while "\n\n\n" in changelog:
        changelog = changelog.replace("\n\n\n", "\n\n")
    return changelog


def get_versions_from_changelog(changelog: str) -> list[Version]:
    """
    Get all versions from headings from the changelog
    """
    return parse_versions(
        [
            line[2:].strip()
            for line in changelog.splitlines()
            if line.startswith(VERSION_HEADING_PREFIX)
        ]
    )


def extract_entry(changelog: str, version: Version) -> str | None:
    """
    Extract an entry for the given version from the changelog
    """
    heading = f"{VERSION_HEADING_PREFIX}{version}\n\n"

    versions = get_versions_from_changelog(changelog)
    previous_version = get_previous_version(versions, version)

    # If there are no versions in the file, return `None`
    if not previous_version and heading not in changelog:
        return None

    previous_heading = (
        f"{VERSION_HEADING_PREFIX}{previous_version}\n\n" if previous_version else None
    )

    if heading not in changelog:
        return None

    start = changelog.index(heading)
    end = changelog.index(previous_heading) if previous_heading else len(changelog)
    return changelog[start:end]


def entry_to_standalone(changelog_entry: str, version: Version) -> str:
    """
    Convert an entry from the CHANGELOG file to a standalone entry (omitting the version)
    """
    return changelog_entry.replace(
        f"{VERSION_HEADING_PREFIX} {version}\n",
        f"{VERSION_HEADING_PREFIX} Changes\n<!-- Generated from the CHANGELOG file -->\n",
    )
