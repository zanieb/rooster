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

### Rebased pull requests

GitHub can associate rebased commits with the pull request that integrated a
release branch instead of their original pull requests. Rooster uses the
`(#123)` suffix in a commit's subject to recover the original merged pull
request when its merge-commit subject matches. If GitHub no longer supplies the
merge commit, the pull request's title and number must match instead. This also
works when GitHub returns no associated pull request. No special labels are
required.

The recovered pull request supplies the changelog entry and version-bump labels;
normal label filtering still applies. References elsewhere in the commit message
are not used.

If some commits in an expanded pull request cannot be resolved, Rooster retains
their associated pull request and prints a warning. Review those commits when
preparing the changelog, especially if the associated pull request is excluded
by an ignored label.

### Caching

Rooster caches responses from the GitHub GraphQL API in `$PWD/.cache`. You may disable this behavior with `ROOSTER_NO_CACHE=1`.
