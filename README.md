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

### Caching

Rooster caches responses from the GitHub GraphQL API in `$PWD/.cache`. You may disable this behavior with `ROOSTER_NO_CACHE=1`.
