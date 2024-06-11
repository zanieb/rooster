from pathlib import Path

import tomllib
import typer

from rooster._changelog import (
    Changelog,
    VersionSection,
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
def release(
    repo: Path = typer.Argument(default=Path(".")),
    bump: BumpType = None,
    update_pyproject: bool = True,
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
    config = Config.from_directory(repo)
    sections = (
        config.changelog_sections.keys() if not only_sections else set(only_sections)
    )
    if without_sections:
        sections -= set(without_sections)

    # Get the last release version
    versions = versions_from_git_tags(config, repo)
    last_version = get_latest_version(versions)
    if last_version:
        typer.echo(f"Found last version tag {last_version}.")
    else:
        typer.echo("It looks like there are no version tags for this project.")

    # Get the commits since the last release
    changes = list(get_commits_between(config, repo, last_version))
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
    changelog_file = Path(changelog_file) or repo.joinpath(config.changelog_file)
    if not changelog_file.exists():
        changelog = Changelog.new()
        typer.echo("Creating new changelog file")
    else:
        # Load the existing changelog
        changelog = Changelog.from_file(changelog_file)

    section = VersionSection.from_pull_requests(
        document=changelog,
        config=config,
        version=new_version,
        pull_requests=pull_requests,
        sections=sections,
    )
    changelog.insert_version_section(section)
    changelog_file.write_text(changelog.to_markdown())
    typer.echo("Updated changelog")

    if update_pyproject:
        try:
            update_pyproject_version(repo.joinpath("pyproject.toml"), new_version)
            typer.echo("Updated version in pyproject.toml")
        except PyProjectError as exc:
            typer.echo(f"Failed to update pyproject.toml: {exc}")
            raise typer.Exit(1)

    if update_version_files:
        for path in config.version_files:
            update_file_version(path, last_version, new_version)
            typer.echo(f"Updated version in {path}")


@app.command()
def changelog(
    repo: Path = typer.Argument(default=Path(".")),
    version: str = None,
    skip_existing: bool = False,
    only_sections: list[str] = typer.Option(
        [], help="Sections to include in the changelog"
    ),
    without_sections: list[str] = typer.Option(
        [], help="Sections to exclude from the changelog"
    ),
):
    """
    Generate the changelog for a version.

    If not provided, the version from the `pyproject.toml` file will be used.
    """
    config = Config.from_directory(repo)
    sections = (
        config.changelog_sections.keys() if not only_sections else set(only_sections)
    )
    if without_sections:
        sections -= set(without_sections)

    if version is None:
        # Get the version from the pyproject file
        pyproject_path = repo.joinpath("pyproject.toml")
        if not pyproject_path.exists():
            typer.echo(
                "No pyproject.toml file found; provide a version to generate an entry for."
            )
            raise typer.Exit(1)

        pyproject = tomllib.loads(pyproject_path.read_text())
        version = pyproject.get("project", {}).get("version")
        if not version:
            typer.echo(
                "No version found in the pyproject.toml; provide a version to generate an entry for."
            )
            raise typer.Exit(1)

        typer.echo(f"Found version {version}")

    # Parse the version
    version = Version(version)

    versions = versions_from_git_tags(config, repo)
    previous_version = get_previous_version(versions, version)
    if previous_version:
        typer.echo(f"Found previous version {previous_version}")

    changes = list(get_commits_between(config, repo, previous_version, version))
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

    # Load the existing changelog
    changelog = Changelog.from_file(repo.joinpath(config.changelog_file))

    if skip_existing:
        existing_section = changelog.get_version_section(version)
        if existing_section:
            existing_entries = existing_section.all_entries()
            previous_count = len(pull_requests)
            pull_requests = [
                pr
                for pr in pull_requests
                if all(f"[#{pr.number}]" not in entry for entry in existing_entries)
            ]
            skipped = previous_count - len(pull_requests)
            if skipped:
                typer.echo(
                    f"Excluding {skipped} pull requests already in changelog entry for {version}"
                )

    section = VersionSection.from_pull_requests(
        document=changelog,
        config=config,
        version=version,
        pull_requests=pull_requests,
        sections=sections,
    )

    print(section.as_document().to_markdown())


@app.command()
def contributors(
    repo: Path = typer.Argument(default=Path(".")),
    version: str = None,
    quiet: bool = False,
):
    """
    Generate a contributor list for a version.

    If not provided, the version from the `pyproject.toml` file will be used.

    Only includes contributors that authored a commit between the given version and one before it.
    """

    def echo(*args):
        if not quiet:
            typer.echo(*args)

    config = Config.from_directory(repo)
    if version is None:
        # Get the version from the pyproject file
        pyproject_path = repo.joinpath("pyproject.toml")
        if not pyproject_path.exists():
            echo(
                "No pyproject.toml file found; provide a version to generate an entry for."
            )
            raise typer.Exit(1)

        pyproject = tomllib.loads(pyproject_path.read_text())
        version = pyproject["project"]["version"]
        echo(f"Found version {version}")

    # Parse the version
    version = Version(version)

    versions = versions_from_git_tags(config, repo)
    previous_version = get_previous_version(versions, version)
    if previous_version:
        echo(f"Found previous version {previous_version}")

    changes = list(get_commits_between(config, repo, previous_version))
    if previous_version:
        echo(f"Found {len(changes)} commits since {previous_version}")
    else:
        echo(f"Found {len(changes)} commits")

    remote = get_remote_url(repo)
    if not remote:
        echo(
            "No remote found; cannot retrieve pull requests to generate changelog entry"
        )
        raise typer.Exit(1)

    owner, repo_name = parse_remote_url(remote)

    echo(f"Retrieving pull requests for changes from {owner}/{repo_name}")
    pull_requests = get_pull_requests_for_commits(owner, repo_name, changes)

    config = Config.from_directory(repo)

    print(generate_contributors(pull_requests, config))


@app.command()
def backfill(
    repo: Path = typer.Argument(default=Path(".")),
    include_first: bool = False,
    clear: bool = False,
    start_version: str = None,
    changelog_file: str = None,
    only_sections: list[str] = typer.Option(
        [], help="Sections to include in the changelog"
    ),
    without_sections: list[str] = typer.Option(
        [], help="Sections to exclude from the changelog"
    ),
):
    """
    Regenerate the entire changelog.
    """
    config = Config.from_directory(repo)
    sections = (
        config.changelog_sections.keys() if not only_sections else set(only_sections)
    )
    if without_sections:
        sections -= set(without_sections)
    start_version = Version(start_version) if start_version else None

    # Generate a changelog entry for the version
    changelog_file = Path(changelog_file) or repo.joinpath(config.changelog_file)

    if clear or not changelog_file.exists():
        changelog = Changelog.new()
        typer.echo("Creating new changelog file")
    else:
        # Load the existing changelog
        changelog = Changelog.from_file(changelog_file)

    remote = get_remote_url(repo)
    if not remote:
        typer.echo(
            "No remote found; cannot retrieve pull requests to generate changelog entry"
        )
        raise typer.Exit(1)

    owner, repo_name = parse_remote_url(remote)
    typer.echo(f"Found remote repository {owner}/{repo_name}")

    versions = versions_from_git_tags(config, repo)
    for i, version in enumerate(versions):
        previous_version = versions[i - 1] if i > 0 else None

        if start_version:
            if version < start_version:
                continue

        changes = list(get_commits_between(config, repo, previous_version, version))
        if previous_version:
            typer.echo(
                f"Found {len(changes)} commits between {previous_version}...{version}"
            )
        else:
            if not include_first:
                continue

            typer.echo(f"Found {len(changes)} commits before {version}")

        typer.echo(f"Retrieving pull requests for {version}...")
        pull_requests = get_pull_requests_for_commits(owner, repo_name, changes)

        section = VersionSection.from_pull_requests(
            document=changelog,
            config=config,
            version=version,
            pull_requests=pull_requests,
            sections=sections,
        )
        changelog.insert_version_section(section)

    changelog_file.write_text(changelog.to_markdown())
    typer.echo("Updated changelog")
