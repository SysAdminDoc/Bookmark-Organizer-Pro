"""Automation-facing CLI status and stream contract tests."""

from __future__ import annotations

import argparse
from pathlib import Path
import shlex
from unittest.mock import Mock, patch

import pytest

from bookmark_organizer_pro.cli import BookmarkCLI
from bookmark_organizer_pro.cli_completions import (
    CompletionArgument,
    CompletionCommand,
    CompletionModel,
    build_completion_model,
    render_bash,
    render_completion_files,
    render_fish,
    render_zsh,
)


def _registered_commands() -> list[str]:
    parser = BookmarkCLI.__new__(BookmarkCLI)._build_parser()
    subparsers = next(
        action
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    return sorted(subparsers.choices)


def test_shell_completions_cover_parser_commands_options_and_choices() -> None:
    model = build_completion_model()
    parser = BookmarkCLI.__new__(BookmarkCLI)._build_parser()
    subparsers = next(
        action
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    rendered = render_completion_files(model)

    assert set(model.command_names) == set(subparsers.choices)
    assert "delete" not in next(command for command in model.commands if command.name == "flow").positionals[0].choices
    assert all(
        command_name in rendered["bop.bash"]
        and command_name in rendered["bop.zsh"]
        and command_name in rendered["bop.fish"]
        for command_name in model.command_names
    )
    for command in model.commands:
        bash_start = rendered["bop.bash"].index(f"        {command.name})")
        zsh_start = rendered["bop.zsh"].index(f"        {command.name})")
        next_commands = [
            rendered["bop.bash"].find(
                f"        {next_command.name})",
                bash_start + 1,
            )
            for next_command in model.commands
            if rendered["bop.bash"].find(
                f"        {next_command.name})",
                bash_start + 1,
            ) >= 0
        ]
        next_zsh_commands = [
            rendered["bop.zsh"].find(
                f"        {next_command.name})",
                zsh_start + 1,
            )
            for next_command in model.commands
            if rendered["bop.zsh"].find(
                f"        {next_command.name})",
                zsh_start + 1,
            ) >= 0
        ]
        bash_end = min(next_commands, default=len(rendered["bop.bash"]))
        zsh_end = min(next_zsh_commands, default=len(rendered["bop.zsh"]))
        bash_branch = rendered["bop.bash"][bash_start:bash_end]
        zsh_branch = rendered["bop.zsh"][zsh_start:zsh_end]
        fish_text = rendered["bop.fish"]
        for argument in command.arguments:
            for option in argument.option_strings:
                assert shlex.quote(option) in bash_branch
                assert option in zsh_branch
                fish_name = option[2:] if option.startswith("--") else option[1:]
                assert fish_name in fish_text
            for choice in argument.choices:
                assert choice in bash_branch
                assert choice in zsh_branch
                assert choice in fish_text


def test_completion_renderers_quote_spaces_non_ascii_and_apostrophes() -> None:
    argument = CompletionArgument(
        dest="value",
        option_strings=("--value",),
        help="Résumé user's value",
        choices=("A space", "café", "user's value"),
        nargs="1",
        required=False,
        takes_value=True,
        file_completion=False,
    )
    model = CompletionModel(
        program="bop",
        global_arguments=(),
        commands=(CompletionCommand("spaced", "Résumé user's command", (argument,)),),
    )

    bash = render_bash(model)
    zsh = render_zsh(model)
    fish = render_fish(model)
    quoted_apostrophe = shlex.quote("user's value")
    assert "'A space'" in bash and "café" in bash and quoted_apostrophe in bash
    assert "A space" in zsh and "café" in zsh and "user" in zsh and "'\"'\"'" in zsh
    assert '"A space"' in fish and "café" in fish and "user's" in fish


def test_generated_completion_files_are_deterministic(tmp_path: Path) -> None:
    rendered = render_completion_files(build_completion_model())
    for filename, content in rendered.items():
        path = tmp_path / filename
        path.write_text(content, encoding="utf-8")
        assert path.read_text(encoding="utf-8") == content
        checked_in = Path(__file__).parents[1] / "scripts" / "completions" / filename
        assert checked_in.read_text(encoding="utf-8") == content


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
