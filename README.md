# Rooster

**This project is a work in progress and not ready for use**

## Usage

### Prepare a new release

Prepares a new release, which:

- Bumps the version
- Generates a changelog entry for the release
- Adds the changelog entry into `CHANGELOG.md`

```
rooster release <path>
```

### Generate a changelog entry for a release

Generates a single changelog entry for the current or given version

```
rooster entry <path> [<version>]
```

### Generate the changelog

Updates the `CHANGELOG.md` file for all releases

```
rooster backfill <path>
```

### Sync the changelog to GitHub Releases

Updates release bodies on GitHub to match the entries in the `CHANGELOG.md` file

```
rooster sync <path>
```
