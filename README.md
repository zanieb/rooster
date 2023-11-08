# Rooster

**This project is a work in progress and not ready for use**

## Usage

### Prepare a new release

Prepares a new release, which:

- Bumps the version
- Generates a changelog entry for the release
- Adds the changelog entry into `CHANGELOG.md`

```
rooster release [<path>] [--bump major|minor|patch]
```

### Generate a changelog entry for a release

Generates a single changelog entry for the current or given version

```
rooster changelog <path> [--version <version>]
```

### Generate the contributor list for a release

Generates a contributor list for the current or given version

```
rooster contributors <path> [--verison <version>]
```

### Caching

Rooster caches responses from the GitHub GraphQL API in `$PWD/.cache`. You may disable this behavior with `ROOSTER_NO_CACHE=1`.