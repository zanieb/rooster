from pathlib import Path

import tomllib
import typer

from rooster._changelog import (
    add_or_update_entry,
    extract_entry,
    generate_changelog,
    generate_contributors,
)
from rooster._config import Config
from rooster._git import get_commits_between, get_remote_url
from rooster._github import get_pull_requests_for_commits, parse_remote_url
from rooster._pyproject import PyProjectError, update_pyproject_version
from rooster._versions import (
    BumpType,
    Version,
    bump_version,
    get_latest_version,
    get_previous_version,
    update_file_version,
    versions_from_git_tags,
)

app = typer.Typer()


@app.command()
def release(repo: Path = typer.Argument(default=Path(".")), bump: BumpType = None):
    """
    Create a new release.

    If no bump type is provided, the bump type will be detected based on the pull request labels.
    """
    config = Config.from_directory(repo)

    # Get the last release version
    versions = versions_from_git_tags(repo)
    last_version = get_latest_version(versions)
    if last_version:
        typer.echo(f"Found last version tag {last_version}.")
    else:
        typer.echo("It looks like there are no version tags for this project.")

    # Get the commits since the last release
    changes = list(get_commits_between(repo, last_version))
    since = "since last release" if last_version else "in the project"
    typer.echo(f"Found {len(changes)} commits {since}.")

    # Determine the GitHub repository to read
    owner, repo_name = parse_remote_url(get_remote_url(repo))

    # Collect pull requests corresponding to each commit
    typer.echo(f"Retrieving pull requests for changes from {owner}/{repo_name}...")
    pull_requests = get_pull_requests_for_commits(owner, repo_name, changes)

    # Collect the unique set of labels changed
    labels = set()
    for pull_request in pull_requests:
        labels.update(pull_request.labels)

    # Determine the version bump type based on the labels or user provided choice
    if bump:
        bump_type = bump
    else:
        bump_type = BumpType.patch
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
    changelog = generate_changelog(pull_requests, config)
    changelog_file = repo.joinpath("CHANGELOG.md")
    if not changelog_file.exists():
        changelog_file.write_text("# Changelog\n\n")
        typer.echo("Created new changelog file")

    update_existing_changelog = changelog_file.read_text()
    new_changelog = add_or_update_entry(
        new_version, update_existing_changelog, changelog
    ).strip()

    changelog_file.write_text(new_changelog)

    typer.echo("Updated changelog")

    try:
        update_pyproject_version(repo.joinpath("pyproject.toml"), new_version)
        typer.echo("Updated version in pyproject.toml")
    except PyProjectError as exc:
        typer.echo(f"Failed to update pyproject.toml: {exc}")
        raise typer.Exit(1)

    for path in config.version_files:
        update_file_version(path, last_version, new_version)
        typer.echo(f"Updated version in {path}")


@app.command()
def changelog(
    repo: Path = typer.Argument(default=Path(".")),
    version: str = None,
    skip_existing: bool = False,
):
    """
    Generate the changelog for a version.

    If not provided, the version from the `pyproject.toml` file will be used.
    """
    if version is None:
        # Get the version from the pyproject file
        pyproject_path = repo.joinpath("pyproject.toml")
        if not pyproject_path.exists():
            typer.echo(
                "No pyproject.toml file found; provide a version to generate an entry for."
            )
            raise typer.Exit(1)

        pyproject = tomllib.loads(pyproject_path.read_text())
        version = pyproject["project"]["version"]
        typer.echo(f"Found version {version}")

    # Parse the version
    version = Version(version)

    versions = versions_from_git_tags(repo)
    previous_version = get_previous_version(versions, version)
    if previous_version:
        typer.echo(f"Found previous version {previous_version}")

    changes = list(get_commits_between(repo, previous_version))
    if previous_version:
        typer.echo(f"Found {len(changes)} commits since {previous_version}")
    else:
        typer.echo(f"Found {len(changes)} commits")

    remote = get_remote_url(repo)
    if not remote:
        typer.echo(
            "No remote found; cannot retrieve pull requests to generate changelog entry"
        )
        raise typer.Exit(1)

    owner, repo_name = parse_remote_url(remote)

    typer.echo(f"Retrieving pull requests for changes from {owner}/{repo_name}")
    pull_requests = get_pull_requests_for_commits(owner, repo_name, changes)

    changelog_file = repo.joinpath("CHANGELOG.md")
    if skip_existing and changelog_file.exists():
        existing_changelog = changelog_file.read_text()
        existing_entry = extract_entry(existing_changelog, version)
        if existing_entry:
            previous_count = len(pull_requests)
            pull_requests = [
                pr for pr in pull_requests if f"[#{pr.number}]" not in existing_entry
            ]
            skipped = previous_count - len(pull_requests)
            if skipped:
                typer.echo(
                    f"Excluding {skipped} pull requests already in changelog entry for {version}"
                )

    config = Config.from_directory(repo)

    changelog = generate_changelog(pull_requests, config)
    print(changelog)


@app.command()
def contributors(
    repo: Path = typer.Argument(default=Path(".")),
    version: str = None,
):
    """
    Generate a contributor list for a version.

    If not provided, the version from the `pyproject.toml` file will be used.

    Only includes contributors that authored a commit between the given version and one before it.
    """
    if version is None:
        # Get the version from the pyproject file
        pyproject_path = repo.joinpath("pyproject.toml")
        if not pyproject_path.exists():
            typer.echo(
                "No pyproject.toml file found; provide a version to generate an entry for."
            )
            raise typer.Exit(1)

        pyproject = tomllib.loads(pyproject_path.read_text())
        version = pyproject["project"]["version"]
        typer.echo(f"Found version {version}")

    # Parse the version
    version = Version(version)

    versions = versions_from_git_tags(repo)
    previous_version = get_previous_version(versions, version)
    if previous_version:
        typer.echo(f"Found previous version {previous_version}")

    changes = list(get_commits_between(repo, previous_version))
    if previous_version:
        typer.echo(f"Found {len(changes)} commits since {previous_version}")
    else:
        typer.echo(f"Found {len(changes)} commits")

    remote = get_remote_url(repo)
    if not remote:
        typer.echo(
            "No remote found; cannot retrieve pull requests to generate changelog entry"
        )
        raise typer.Exit(1)

    owner, repo_name = parse_remote_url(remote)

    typer.echo(f"Retrieving pull requests for changes from {owner}/{repo_name}")
    pull_requests = get_pull_requests_for_commits(owner, repo_name, changes)

    config = Config.from_directory(repo)

    print(generate_contributors(pull_requests, config))
