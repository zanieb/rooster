# Rooster

**This interface provided by this tool is unstable, we highly recommend pinning your version.**

## Usage

### Prepare a new release

Prepares a new release, which:

- Determines a new version number
- Generates a changelog entry for the release and adds to `CHANGELOG.md`
- Updates the version number in `pyproject.toml`

```
rooster release [<path>] [--bump major|minor|patch]
```

### Generate a changelog entry for a release

Generates a changelog entry for the current or given version

```
rooster changelog [<path>] [--version <version>]
```

### Generate the contributor list for a release

Generates a contributor list for the current or given version

```
rooster contributors [<path>] [--verison <version>]
```

### Caching

Rooster caches responses from the GitHub GraphQL API in `$PWD/.cache`. You may disable this behavior with `ROOSTER_NO_CACHE=1`.
