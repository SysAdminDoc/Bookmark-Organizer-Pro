"""Automation-facing CLI status and stream contract tests."""

from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from bookmark_organizer_pro.cli import BookmarkCLI


def _registered_commands() -> list[str]:
    parser = BookmarkCLI.__new__(BookmarkCLI)._build_parser()
    subparsers = next(
        action
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    return sorted(subparsers.choices)


@pytest.mark.parametrize("command_name", _registered_commands())
def test_every_registered_command_has_a_handler(command_name: str) -> None:
    parser = BookmarkCLI.__new__(BookmarkCLI)._build_parser()
    subparsers = next(
        action
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    )

    assert callable(subparsers.choices[command_name].get_default("func"))


@pytest.mark.parametrize(
    ("arguments", "expected_code", "expected_error"),
    [
        (["definitely-not-a-command"], 2, "Unknown command"),
        (["add"], 2, "usage: add"),
        (["import-pocket"], 2, "usage: import-pocket"),
        (["structured", "999"], 1, "Bookmark not found"),
    ],
)
def test_usage_and_not_found_failures_use_stderr(
    arguments: list[str],
    expected_code: int,
    expected_error: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = BookmarkCLI.__new__(BookmarkCLI)
    cli.bookmark_manager = Mock()
    cli.bookmark_manager.get_bookmark.return_value = None

    assert cli.run(arguments) == expected_code
    captured = capsys.readouterr()
    assert expected_error in captured.err
    assert expected_error not in captured.out


def test_handler_exception_and_interrupt_have_stable_codes(
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = BookmarkCLI.__new__(BookmarkCLI)
    cli.bookmark_manager = Mock()
    cli.category_manager = Mock()
    cli.tag_manager = Mock()
    cli._cmd_categories = Mock(side_effect=RuntimeError("storage unavailable"))
    assert cli.run(["categories"]) == 1
    assert "storage unavailable" in capsys.readouterr().err

    cli._cmd_categories = Mock(side_effect=KeyboardInterrupt)
    assert cli.run(["categories"]) == 130
    assert "Interrupted" in capsys.readouterr().err


def test_recovery_decrypt_is_atomic_on_publish_failure(tmp_path: Path) -> None:
    from bookmark_organizer_pro.services.encryption import (
        EncryptedStore,
        generate_recovery_key,
    )

    if not EncryptedStore.available():
        pytest.skip("cryptography is not installed")
    recovery_key = generate_recovery_key()
    source = tmp_path / "bookmarks.json.enc"
    destination = tmp_path / "bookmarks.json"
    source.write_bytes(
        EncryptedStore("test passphrase").encrypt_with_recovery(
            b'{"bookmarks": []}', recovery_key
        )
    )
    destination.write_bytes(b"previous library")
    cli = BookmarkCLI.__new__(BookmarkCLI)

    with patch(
        "bookmark_organizer_pro.services.encryption.os.replace",
        side_effect=OSError("publish denied"),
    ):
        code = cli.run(
            [
                "decrypt",
                str(source),
                str(destination),
                "--recovery-key",
                recovery_key,
            ]
        )

    assert code == 1
    assert destination.read_bytes() == b"previous library"
    assert list(tmp_path.glob("*.tmp")) == []
