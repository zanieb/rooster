# Rooster

**This project is a work in progress and not ready for use**

## Usage

### Prepare a new release

```
rooster release [<path>] [--bump major|minor|patch]
```

Prepares a new release, which:

- Determines a new version number
- Generates a changelog entry for the release and adds to `CHANGELOG.md`
- Updates the version number in `pyproject.toml`

### Generate a changelog entry for a release

Generates a changelog entry for the current or given version

```
rooster changelog <path> [--version <version>] [--write] [--no-merge]
```

If a changelog entry already exists for the given version, the contents will be merged to produce the new entry.
Any pull requests already in the changelog will be left unchanged, allowing you to easily update the entry with the
latest pull requests without reverting edits. The `--no-merge` flag can be used to disable this behavior.

By default, the changelog entry is written to stdout. The `--write` flag can be passed to update the changelog
file.

### Generate the contributor list for a release

Generates a contributor list for the current or given version

```
rooster contributors <path> [--verison <version>]
```

### Caching

Rooster caches responses from the GitHub GraphQL API in `$PWD/.cache`. You may disable this behavior with `ROOSTER_NO_CACHE=1`.