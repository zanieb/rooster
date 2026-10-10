from types import SimpleNamespace

import pytest

from rooster._github import GitHubGraphQLError, get_pull_requests_for_commits


@pytest.mark.parametrize("labels", [(), ("release",), ("tracking",)])
def test_rebased_commit_recovers_original_labels(github_api, labels):
    umbrella = github_api.pull_request(10, labels=labels)
    original = github_api.pull_request(1, labels=("breaking",))
    commit = github_api.commit("Change 1 (#1)", umbrella)

    result = get_pull_requests_for_commits("owner", "repo", [commit])

    assert len(result) == 1
    assert result[0].number == 1
    assert result[0].labels == {"breaking"}
    assert result[0].url == original["url"]
    assert github_api.lookups == [1]


def test_matching_association_needs_no_lookup(github_api):
    original = github_api.pull_request(1)
    commit = github_api.commit("Change 1 (#1)\n\nRelated to (#2)", original)

    result = get_pull_requests_for_commits("owner", "repo", [commit])

    assert [pr.number for pr in result] == [1]
    assert not github_api.lookups
    assert len(github_api.requests) == 1


def test_missing_association_uses_commit_reference(github_api):
    github_api.pull_request(1)
    commit = github_api.commit("Change 1 (#1)")

    result = get_pull_requests_for_commits("owner", "repo", [commit])

    assert [pr.number for pr in result] == [1]


@pytest.mark.parametrize(
    "message",
    [
        "Change\n\nRelated to (#1)",
        "Related to (#1), but a different change",
        "Change (#0)",
    ],
)
def test_other_references_are_not_used(github_api, message):
    associated = github_api.pull_request(10)
    commit = github_api.commit(message, associated)

    result = get_pull_requests_for_commits("owner", "repo", [commit])

    assert [pr.number for pr in result] == [10]
    assert not github_api.lookups


def test_final_subject_reference_is_used(github_api):
    subject = "Follow up on (#1) with another change (#2)"
    github_api.pull_request(2, subject=subject)
    commit = github_api.commit(subject)

    result = get_pull_requests_for_commits("owner", "repo", [commit])

    assert [pr.number for pr in result] == [2]
    assert github_api.lookups == [2]


@pytest.mark.parametrize(
    "reason", ["missing", "unmerged", "different-subject", "no-merge-commit"]
)
def test_unresolved_reference_retains_association(github_api, capsys, reason):
    associated = github_api.pull_request(10)
    if reason != "missing":
        candidate = github_api.pull_request(1)
        if reason == "unmerged":
            candidate["merged"] = False
        elif reason == "different-subject":
            candidate["mergeCommit"]["message"] = "Unrelated work (#1)"
        else:
            candidate["mergeCommit"] = None
            candidate["title"] = "Unrelated work"
    commit = github_api.commit("Change 1 (#1)", associated)

    result = get_pull_requests_for_commits("owner", "repo", [commit])

    assert [pr.number for pr in result] == [10]
    assert f"could not match commit {commit.id}" in capsys.readouterr().err


def test_old_merged_pr_without_merge_commit_uses_matching_title(github_api):
    associated = github_api.pull_request(10)
    original = github_api.pull_request(1, labels=("breaking",))
    original["mergeCommit"] = None
    commit = github_api.commit("Change 1 (#1)", associated)

    result = get_pull_requests_for_commits("owner", "repo", [commit])

    assert [pr.number for pr in result] == [1]
    assert result[0].labels == {"breaking"}


def test_available_merge_commit_takes_precedence_over_current_title(github_api):
    associated = github_api.pull_request(10)
    original = github_api.pull_request(1)
    original["title"] = "Edited title"
    commit = github_api.commit("Change 1 (#1)", associated)

    result = get_pull_requests_for_commits("owner", "repo", [commit])

    assert [pr.number for pr in result] == [1]


@pytest.mark.parametrize("found", [True, False])
def test_repeated_references_are_cached(github_api, found):
    associated = github_api.pull_request(10)
    if found:
        github_api.pull_request(1)
    commits = [github_api.commit("Change 1 (#1)", associated) for _ in range(2)]

    result = get_pull_requests_for_commits("owner", "repo", commits)

    assert [pr.number for pr in result] == ([1, 1] if found else [10, 10])
    assert github_api.lookups == [1]


def test_references_with_different_subjects_are_checked_separately(github_api):
    associated = github_api.pull_request(10)
    github_api.pull_request(1)
    commits = [
        github_api.commit("Change 1 (#1)", associated),
        github_api.commit("Revert change 1 (#1)", associated),
    ]

    result = get_pull_requests_for_commits("owner", "repo", commits)

    assert [pr.number for pr in result] == [1, 10]


def test_unreferenced_commits_in_expanded_pr_warn_across_pages(github_api, capsys):
    associated = github_api.pull_request(10)
    github_api.pull_request(1)
    github_api.page_size = 1
    raw = github_api.commit("Vendor a dependency", associated)
    rebased = github_api.commit("Change 1 (#1)", associated)

    result = get_pull_requests_for_commits("owner", "repo", [raw, rebased])

    assert [pr.number for pr in result] == [10, 1]
    warning = capsys.readouterr().err
    assert raw.id in warning
    assert associated["url"] in warning
    assert "reviewing the changelog" in warning


def test_direct_commits_in_ordinary_pr_do_not_warn(github_api, capsys):
    associated = github_api.pull_request(10)
    commit = github_api.commit("Vendor a dependency", associated)

    result = get_pull_requests_for_commits("owner", "repo", [commit])

    assert [pr.number for pr in result] == [10]
    assert not capsys.readouterr().err


@pytest.mark.parametrize(
    "error",
    [
        {"type": "FORBIDDEN", "path": ["repository", "pullRequest"]},
        {"type": "NOT_FOUND", "path": ["repository"]},
    ],
)
def test_api_errors_are_not_treated_as_missing_prs(github_api, error):
    github_api.errors = [error]
    commit = github_api.commit("Change 1 (#1)")

    with pytest.raises(GitHubGraphQLError):
        get_pull_requests_for_commits("owner", "repo", [commit])


def test_deleted_author_can_be_recovered(github_api):
    github_api.pull_request(1, author=None)
    commit = github_api.commit("Change 1 (#1)")

    result = get_pull_requests_for_commits("owner", "repo", [commit])

    assert result[0].author == "ghost"


def test_commits_outside_release_range_are_not_resolved(github_api):
    associated = github_api.pull_request(10)
    current = github_api.commit("Direct change", associated)
    github_api.commit("Old change (#1)")

    result = get_pull_requests_for_commits("owner", "repo", [current])

    assert [pr.number for pr in result] == [10]
    assert not github_api.lookups


def test_unpublished_leading_commit_is_skipped(github_api):
    associated = github_api.pull_request(10)
    published = github_api.commit("Published change", associated)
    unpublished = SimpleNamespace(id="f" * 40)
    github_api.missing_commits.add(unpublished.id)

    result = get_pull_requests_for_commits("owner", "repo", [unpublished, published])

    assert [pr.number for pr in result] == [10]


def test_empty_commit_list_does_not_query_github(github_api):
    assert get_pull_requests_for_commits("owner", "repo", []) == []
    assert not github_api.requests


def test_history_pagination_counts_requested_commits(github_api):
    github_api.page_size = 1
    first = github_api.commit("Change 1 (#1)", github_api.pull_request(1))
    github_api.commit("Outside range (#2)", github_api.pull_request(2))
    last = github_api.commit("Change 3 (#3)", github_api.pull_request(3))
    github_api.commit("Older change (#4)", github_api.pull_request(4))

    result = get_pull_requests_for_commits("owner", "repo", [first, last])

    assert [pr.number for pr in result] == [1, 3]
    assert len(github_api.requests) == 3


def test_duplicate_commit_inputs_do_not_extend_history_pagination(github_api):
    github_api.page_size = 1
    commit = github_api.commit("Change 1 (#1)", github_api.pull_request(1))
    github_api.commit("Older change (#2)", github_api.pull_request(2))

    result = get_pull_requests_for_commits("owner", "repo", [commit, commit])

    assert [pr.number for pr in result] == [1]
    assert len(github_api.requests) == 1


def test_unassociated_direct_commit_warns(github_api, capsys):
    commit = github_api.commit("A direct change")
    assert get_pull_requests_for_commits("owner", "repo", [commit]) == []
    warning = capsys.readouterr().err
    assert commit.id in warning
    assert "no pull request found" in warning
    assert "omitted" in warning


def test_unpublished_commit_warns(github_api, capsys):
    commit = SimpleNamespace(id="f" * 40)
    github_api.missing_commits.add(commit.id)
    assert get_pull_requests_for_commits("owner", "repo", [commit]) == []
    warning = capsys.readouterr().err
    assert commit.id in warning
    assert "not available on GitHub" in warning


def test_requested_commit_missing_from_history_warns(github_api, capsys):
    found = github_api.commit("Change 1 (#1)", github_api.pull_request(1))
    missing = SimpleNamespace(id="f" * 40)
    result = get_pull_requests_for_commits("owner", "repo", [found, missing])
    assert [pr.number for pr in result] == [1]
    warning = capsys.readouterr().err
    assert missing.id in warning
    assert "not found in GitHub history" in warning
