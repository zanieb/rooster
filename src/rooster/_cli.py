from pathlib import Path

import typer

from rooster._changelog import (
    Changelog,
    VersionSection,
)
from rooster._config import Config
from rooster._git import (
    GitLookupError,
    get_commit_for_version,
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
    update_version_file,
    versions_from_git_tags,
)

app = typer.Typer(pretty_exceptions_enable=False)


@app.command()
def release(
    directory: Path = typer.Argument(default=Path(".")),
    submodule: Path = None,
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
    repo = repo_from_path(directory)
    versions = versions_from_git_tags(config, repo)
    last_version = get_latest_version(versions)
    last_version_commit = (
        get_commit_for_version(config, repo, last_version)
        if last_version
        else get_initial_commit(repo)
    )
    latest_commit = get_latest_commit(repo)
    if last_version:
        typer.echo(f"Found last version tag {last_version}")
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

    if submodule:
        submodule = repo_from_path(submodule)
        submodule_path = Path(submodule.workdir).relative_to(repo.workdir)
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
        typer.echo(f"Found {len(changes)} commits {since}.")

        # Determine the GitHub repository to read
        remote = get_remote_url(submodule)
        if remote is None:
            typer.echo("Failed to determine remote for submodule.")
            raise typer.Exit(1)
        owner, repo_name = parse_remote_url(remote)

        # Collect pull requests corresponding to each commit
        typer.echo(f"Retrieving pull requests for changes from {owner}/{repo_name}...")
        pull_requests += get_pull_requests_for_commits(
            owner, repo_name, submodule_changes
        )

    if not pull_requests:
        typer.echo("No pull requests found, aborting!")
        raise typer.Exit(1)

    # Filter the pull requests to relevant labels
    if config.required_labels:
        prefilter_count = len(pull_requests)
        pull_requests = [
            pull_request
            for pull_request in pull_requests
            if pull_request.labels.intersection(config.required_labels)
        ]
        if not pull_requests:
            typer.echo("No pull requests found with required labels, aborting!")
            raise typer.Exit(1)
        typer.echo(
            f"Found {len(pull_requests)} pull requests with required labels (out of {prefilter_count})."
        )

    # Collect the unique set of labels changed
    labels = set()
    for pull_request in pull_requests:
        labels.update(pull_request.labels)

    # Determine the version bump type based on the labels or user provided
    # choice
    if version:
        new_version = version
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
        for version_file in config.version_files:
            update_version_file(
                version_file, last_version or Version("0.0.0"), new_version
            )
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
    )

    # TODO(zanieb): Implement smart merging here
    existing = changelog.get_version_section(version)
    if existing:
        typer.echo(f"Version {version} already exists in changelog, updating...")

    changelog.insert_version_section(section)
    changelog_file.write_text(changelog.to_markdown())
