from pathlib import Path

import typer

from rooster._changelog import (
    Changelog,
    VersionSection,
)
from rooster._config import Config, SubstitutionEntry
from rooster._git import (
    GitLookupError,
    get_commit_for_tag,
    get_commits_between_commits,
    get_initial_commit,
    get_latest_commit,
    get_remote_url,
    get_submodule_commit,
    repo_from_path,
)
from rooster._github import PullRequest, get_pull_requests_for_commits, parse_remote_url
from rooster._versions import (
    BumpType,
    Version,
    bump_version,
    get_latest_version,
    process_substitutions,
    update_version_file,
    versions_from_git_tags,
)

app = typer.Typer(pretty_exceptions_enable=False)


@app.command()
def release(
    directory: Path = typer.Argument(default=Path(".")),
    bump: BumpType = None,
    version: str = None,
    update_version_files: bool = True,
    changelog_file: str = None,
    only_sections: list[str] = typer.Option(
        [], help="Sections to include in the changelog"
    ),
    without_sections: list[str] = typer.Option(
        [], help="Sections to exclude from the changelog"
    ),
):
    """
    Create a new release.

    - Bumps the version in version files
    - Updates the changelog with changes from the latest version

    If no bump type is provided, the bump type will be detected based on the pull request labels.
    """
    config = Config.from_directory(directory)

    if bump and version:
        typer.echo("You cannot specify both a version and a bump type.")
        raise typer.Exit(1)

    # Get the last release version
    typer.echo(f"Inspecting project at {directory.resolve()}")
    repo = repo_from_path(directory)
    version_tags = versions_from_git_tags(config, repo)
    last_version = get_latest_version(version_tags.keys())
    last_version_commit = (
        get_commit_for_tag(repo, version_tags[last_version])
        if last_version
        else get_initial_commit(repo)
    )
    latest_commit = get_latest_commit(repo)
    if last_version:
        tag_display = (
            f" (tag: {version_tags[last_version]})"
            if version_tags[last_version] != str(last_version)
            else ""
        )
        typer.echo(f"Found last version {last_version}{tag_display}")
        last_display = f"{str(last_version_commit.id)[:8]} ({last_version})"
    else:
        typer.echo(
            "It looks like there are no version tags for this project, release will include all commits"
        )
        last_display = f"{str(last_version_commit.id)[:8]} (initial commit)"

    # Get the commits since the last release
    try:
        typer.echo(
            f"Collecting commits between {last_display} and {str(latest_commit.id)[:8]} (HEAD)..."
        )
        changes = list(
            get_commits_between_commits(repo, last_version_commit, latest_commit)
        )
    except GitLookupError as exc:
        typer.echo(f"Failed to find commits: {exc}")
        raise typer.Exit(1)
    since = "since last release" if last_version else "in the project"
    typer.echo(f"Found {len(changes)} commits {since}.")

    # Determine the GitHub repository to read
    remote = get_remote_url(repo)
    if remote is None:
        typer.echo("Failed to determine remote for repository.")
        raise typer.Exit(1)
    owner, repo_name = parse_remote_url(remote)

    # Collect pull requests corresponding to each commit
    typer.echo(f"Retrieving pull requests for changes from {owner}/{repo_name}...")
    pull_requests = get_pull_requests_for_commits(owner, repo_name, changes)

    for submodule_path in config.submodules:
        typer.echo(f"Inspecting submodule `{submodule_path.name}`")
        submodule = repo_from_path(submodule_path)
        last_submodule_commit = get_submodule_commit(
            repo, last_version_commit, submodule
        )
        latest_submodule_commit = get_latest_commit(submodule)
        typer.echo(
            f"Collecting commits for submodule `{submodule_path}` between {str(last_submodule_commit.id)[:8]} and {str(latest_submodule_commit.id)[:8]}..."
        )
        try:
            submodule_changes = list(
                get_commits_between_commits(
                    submodule,
                    last_submodule_commit,
                    latest_submodule_commit,
                )
            )
        except GitLookupError as exc:
            typer.echo(f"Failed to find commits: {exc}")
            raise typer.Exit(1)
        since = (
            f"since last release for submodule `{submodule_path}`"
            if last_version
            else f"for submodule `{submodule_path}`"
        )
        typer.echo(f"Found {len(submodule_changes)} commits {since}.")

        # Determine the GitHub repository to read
        remote = get_remote_url(submodule)
        if remote is None:
            typer.echo("Failed to determine remote for submodule.")
            raise typer.Exit(1)
        owner, repo_name = parse_remote_url(remote)

        # Collect pull requests corresponding to each commit
        typer.echo(f"Retrieving pull requests for changes from {owner}/{repo_name}...")
        submodule_pull_requests = get_pull_requests_for_commits(
            owner, repo_name, submodule_changes
        )

        # Filter the pull requests to relevant labels
        if required_labels := config.required_labels_for_submodule(submodule_path):
            prefilter_count = len(submodule_pull_requests)
            submodule_pull_requests = [
                pull_request
                for pull_request in submodule_pull_requests
                if pull_request.labels.intersection(required_labels)
            ]
            if submodule_pull_requests:
                typer.echo(
                    f"Found {len(submodule_pull_requests)} (of {prefilter_count}) pull requests with required labels."
                )
            else:
                typer.echo(
                    f"No pull requests found with required labels for submodule `{submodule_path}`"
                )

        if ignored_labels := config.ignored_labels_for_submodule(submodule_path):
            prefilter_count = len(submodule_pull_requests)
            submodule_pull_requests = [
                pull_request
                for pull_request in submodule_pull_requests
                if not pull_request.labels.intersection(ignored_labels)
            ]
            if submodule_pull_requests:
                typer.echo(
                    f"Found {len(submodule_pull_requests)} (of {prefilter_count}) pull requests after applying ignored labels."
                )
            else:
                typer.echo(
                    f"No pull requests found for submodule `{submodule_path}` after applying ignored labels."
                )

        pull_requests.extend(submodule_pull_requests)

    if not pull_requests:
        typer.echo("No pull requests found, aborting!")
        raise typer.Exit(1)

    # Filter the pull requests to relevant labels
    if required_labels := config.global_required_labels():
        prefilter_count = len(pull_requests)
        pull_requests = [
            pull_request
            for pull_request in pull_requests
            if pull_request.labels.intersection(required_labels)
        ]
        if not pull_requests:
            typer.echo("No pull requests found with required labels, aborting!")
            raise typer.Exit(1)
        typer.echo(
            f"Found {len(pull_requests)} (of {prefilter_count}) pull requests with required labels."
        )

    if ignored_labels := config.global_ignored_labels():
        prefilter_count = len(pull_requests)
        pull_requests = [
            pull_request
            for pull_request in pull_requests
            if not pull_request.labels.intersection(ignored_labels)
        ]
        if not pull_requests:
            typer.echo(
                "No pull requests found after applying ignored labels, aborting!"
            )
            raise typer.Exit(1)
        typer.echo(
            f"Found {len(pull_requests)} (of {prefilter_count}) pull requests after applying ignored labels."
        )

    # Collect the unique set of labels changed
    labels = set()
    for pull_request in pull_requests:
        labels.update(pull_request.labels)

    # Determine the version bump type based on the labels or user provided
    # choice
    if version:
        new_version = Version(version)
    else:
        if bump:
            bump_type = bump
        else:
            bump_type = config.default_bump_type
            for label in config.major_labels:
                if label in labels:
                    typer.echo(f"Detected major version change due label {label}")
                    bump_type = BumpType.major
                    break

            for label in config.minor_labels:
                if label in labels:
                    typer.echo(f"Detected minor version change due label {label}")
                    bump_type = BumpType.minor
                    break

            if bump_type == BumpType.patch:
                typer.echo(
                    "Detected patch version change — did not see any major or minor labels"
                )
        new_version = bump_version(
            # If there is no previous version, start at 0.0.0
            last_version or Version("0.0.0"),
            bump_type,
        )

    if config.trim_title_prefixes:
        # TODO(zanieb): This is a little sloppy, could be written more simply
        trimmed_pull_requests = []
        for pull_request in pull_requests:
            for prefix in config.trim_title_prefixes:
                if pull_request.title.startswith(prefix):
                    pull_request = pull_request.with_title(
                        pull_request.title[len(prefix) :].strip()
                    )
            trimmed_pull_requests.append(pull_request)
        pull_requests = trimmed_pull_requests

    typer.echo(f"Using new version {new_version}")

    # Generate a changelog entry for the version
    changelog_file = (
        Path(changelog_file)
        if changelog_file
        else directory.joinpath(config.changelog_file)
    )
    update_changelog(
        changelog_file,
        version=new_version,
        config=config,
        pull_requests=pull_requests,
        only_sections=only_sections,
        without_sections=without_sections,
    )
    typer.echo("Updated changelog")

    if update_version_files:
        old_version = last_version or Version("0.0.0")
        for version_file in config.version_files:
            if isinstance(version_file, SubstitutionEntry):
                for match in directory.glob(version_file.target):
                    process_substitutions(
                        match, old_version, new_version, version_file.replace
                    )
            else:
                update_version_file(version_file, old_version, new_version)
            typer.echo(f"Updated version in {version_file}")


# When only one command exists, typer will treat it as the root command instead
# of a child.
@app.command(hidden=True)
def noop(): ...


def update_changelog(
    changelog_file: Path,
    version: Version,
    config: Config,
    pull_requests: list[PullRequest],
    only_sections: set[str] = set(),
    without_sections: set[str] = set(),
    release_date=None,
):
    if not changelog_file.exists():
        changelog = Changelog.new()
        typer.echo("Creating new changelog file")
    else:
        # Load the existing changelog
        changelog = Changelog.from_file(changelog_file)

    section = VersionSection.from_pull_requests(
        document=changelog,
        config=config,
        version=version,
        pull_requests=pull_requests,
        only_sections=only_sections,
        without_sections=without_sections,
        release_date=release_date,
    )

    # TODO(zanieb): Implement smart merging here
    existing = changelog.get_version_section(config, version)
    if existing:
        typer.echo(f"Version {version} already exists in changelog, updating...")

    changelog.insert_version_section(section)
    changelog_file.write_text(changelog.to_markdown())
