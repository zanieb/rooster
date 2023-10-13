from pathlib import Path

import tomllib
import typer

from rooster._changelog import (
    add_or_update_entry,
    entry_to_standalone,
    extract_entry,
    generate_changelog,
    get_versions_from_changelog,
)
from rooster._config import get_config
from rooster._git import get_commits_between, get_remote_url
from rooster._github import get_pull_requests_for_commits, get_release, parse_remote_url
from rooster._versions import (
    Version,
    bump_version,
    get_latest_version,
    get_previous_version,
    get_versions,
)

app = typer.Typer()


@app.command()
def release(repo: Path = typer.Argument(default=Path("."))):
    """
    Create a new release.
    """
    versions = get_versions(repo)
    previous_version = get_latest_version(versions)
    typer.echo(f"Found previous version {previous_version}")

    changes = list(get_commits_between(repo, previous_version))
    typer.echo(f"Found {len(changes)} commits since last release")

    owner, repo_name = parse_remote_url(get_remote_url(repo))

    typer.echo(f"Retrieving pull requests for changes from {owner}/{repo_name}")
    pull_requests = get_pull_requests_for_commits(owner, repo_name, changes)

    labels = set()
    for pull_request in pull_requests:
        labels.update(pull_request.labels)

    config = get_config(repo)
    bump_type = "patch"
    for label in config.major_labels:
        if label in labels:
            typer.echo(f"Detected major version change due label {label}")
            bump_type = "major"
            break

    for label in config.minor_labels:
        if label in labels:
            typer.echo(f"Detected minor version change due label {label}")
            bump_type = "minor"
            break

    if bump_type == "patch":
        typer.echo(
            "Detected patch version change — did not see any major or minor labels"
        )

    new_version = bump_version(
        # If there is no previous version, start at 0.0.0
        previous_version or Version("0.0.0"),
        bump_type,
    )
    typer.echo(f"Creating new version {new_version}")

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


@app.command()
def entry(repo: Path = typer.Argument(default=Path(".")), version: str = None):
    """
    Generate a changelog entry for a version.
    If not provided, the current local version from the pyproject.toml file will be used.
    """
    if version is None:
        # Get the version from the pyproject file
        pyproject = tomllib.loads(repo.joinpath("pyproject.toml").read_text())
        version = pyproject["project"]["version"]
        typer.echo(f"Found version {version}")

    # Parse the version
    version = Version(version)

    versions = get_versions(repo)
    previous_version = get_previous_version(versions, version)
    typer.echo(f"Found previous version {previous_version}")

    changes = list(get_commits_between(repo, previous_version))
    typer.echo(f"Found {len(changes)} commits since {previous_version}")

    owner, repo_name = parse_remote_url(get_remote_url(repo))

    typer.echo(f"Retrieving pull requests for changes from {owner}/{repo_name}")
    pull_requests = get_pull_requests_for_commits(owner, repo_name, changes)

    config = get_config(repo)

    changelog = generate_changelog(pull_requests, config)
    print(changelog)


@app.command()
def update(
    repo: Path = typer.Argument(default=Path(".")),
    update_existing: bool = False,
    oldest: str = None,
):
    """
    Update the changelog with all of the releases in the repository.
    Releases are discovered by tags parsable as versions.
    """
    tag_versions = get_versions(repo)
    changelog_file = repo.joinpath("CHANGELOG.md")
    if not changelog_file.exists():
        changelog_file.write_text("# Changelog\n\n")
        typer.echo("Created new changelog file")

    changelog = changelog_file.read_text()
    changelog_versions = get_versions_from_changelog(changelog)

    config = get_config(repo)
    owner, repo_name = parse_remote_url(get_remote_url(repo))

    for version in sorted(tag_versions, reverse=True):
        if oldest is not None and Version(oldest) > version:
            typer.echo(f"Reached oldest version {oldest}, stopping")
            break

        if version in changelog_versions and not update_existing:
            typer.echo(f"Skipping existing version {version}")
            continue
        commits = list(
            get_commits_between(
                repo,
                get_previous_version(tag_versions, version),
                version,
            )
        )

        typer.echo(
            f"Generating changelog entry for {version} with {len(commits)} changes"
        )

        pull_requests = get_pull_requests_for_commits(owner, repo_name, commits)

        changelog = add_or_update_entry(
            version, changelog, generate_changelog(pull_requests, config)
        )

        # Write each entry as we go because I'm developing and impatient :)
        changelog_file.write_text(changelog)

    typer.echo("Updated changelog!")


@app.command()
def sync(
    repo: Path = typer.Argument(default=Path(".")),
    update_existing: bool = False,
    check: bool = False,
    oldest: str = None,
):
    """
    Update releases on GitHub with the local changelog entries.
    """
    changelog_file = repo.joinpath("CHANGELOG.md")
    if not changelog_file.exists():
        typer.echo(
            "Changelog file does not exist. Consider using `rooster backfill` first."
        )
        return

    changelog = changelog_file.read_text()
    changelog_versions = get_versions_from_changelog(changelog)

    owner, repo_name = parse_remote_url(get_remote_url(repo))

    changed = 0
    for version in sorted(changelog_versions, reverse=True):
        if oldest is not None and Version(oldest) > version:
            typer.echo(f"Reached oldest version {oldest}, stopping")
            break

        release = get_release(owner, repo_name, f"v{version}")
        if not release:
            typer.echo(f"Skipping release {version} not found on GitHub")
            continue

        local_entry = entry_to_standalone(extract_entry(changelog, version), version)
        if release.body == local_entry:
            typer.echo(f"Release {version} is up to date")
            continue

        if release.body and not update_existing:
            typer.echo(f"Skipping release {version} with existing body")
            continue

        changed += 1

        if check:
            typer.echo(f"Would update release {version} ")
            continue

        typer.echo(f"Updating release {version}")
        print(local_entry)

    if check:
        typer.echo(f"Would have updated {changed} releases.")
        if changed > 0:
            raise typer.Exit(1)
    else:
        typer.echo(f"Updated {changed} releases.")
