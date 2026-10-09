from types import SimpleNamespace

import pytest

from rooster import _github


@pytest.fixture(autouse=True)
def token_environment(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    _github.get_github_token.cache_clear()
    yield
    _github.get_github_token.cache_clear()


@pytest.mark.parametrize("name", ["GITHUB_TOKEN", "GH_TOKEN"])
def test_environment_token_does_not_require_cli(monkeypatch, name):
    monkeypatch.setenv(name, "environment-token")
    monkeypatch.setattr(_github.shutil, "which", lambda _: None)
    assert _github.get_github_token() == "environment-token"


def test_github_token_keeps_precedence(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "project-token")
    monkeypatch.setenv("GH_TOKEN", "cli-token")
    assert _github.get_github_token() == "project-token"


def test_cli_token_is_returned_without_status_parsing(monkeypatch, capsys):
    monkeypatch.setattr(_github.shutil, "which", lambda _: "/usr/bin/gh")

    def run(command, **kwargs):
        assert command == ["gh", "auth", "token"]
        assert kwargs == {"capture_output": True, "check": False}
        return SimpleNamespace(returncode=0, stdout=b" cli-token\n", stderr=b"")

    monkeypatch.setattr(_github.subprocess, "run", run)
    assert _github.get_github_token() == "cli-token"
    assert capsys.readouterr() == ("", "")


def test_cli_failure_never_prints_command_output(monkeypatch, capsys):
    monkeypatch.setattr(_github.shutil, "which", lambda _: "/usr/bin/gh")
    monkeypatch.setattr(
        _github.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1,
            stdout=b"Token: credential-that-must-not-be-logged\n",
            stderr=b"credential-that-must-not-be-logged",
        ),
    )
    with pytest.raises(RuntimeError) as exc:
        _github.get_github_token()
    assert "credential-that-must-not-be-logged" not in str(exc.value)
    assert capsys.readouterr() == ("", "")


def test_empty_cli_token_is_rejected(monkeypatch):
    monkeypatch.setattr(_github.shutil, "which", lambda _: "/usr/bin/gh")
    monkeypatch.setattr(
        _github.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=b"\n", stderr=b""),
    )
    with pytest.raises(RuntimeError, match="empty"):
        _github.get_github_token()


def test_missing_cli_gives_token_configuration_hint(monkeypatch):
    monkeypatch.setattr(_github.shutil, "which", lambda _: None)
    with pytest.raises(RuntimeError, match="GITHUB_TOKEN or GH_TOKEN"):
        _github.get_github_token()
