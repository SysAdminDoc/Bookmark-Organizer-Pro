"""Parser-derived shell completion model and renderers.

The CLI parser is the only command/option source of truth.  This module keeps
the shell-specific output deliberately boring: each renderer receives the
same immutable model, so a new argparse command cannot silently exist without
being represented in the generated completion files.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import shlex
from typing import Iterable


@dataclass(frozen=True)
class CompletionArgument:
    """The shell-relevant portion of one argparse action."""

    dest: str
    option_strings: tuple[str, ...]
    help: str
    choices: tuple[str, ...]
    nargs: str
    required: bool
    takes_value: bool
    file_completion: bool

    @property
    def positional(self) -> bool:
        """Whether this action is filled without an option name."""

        return not self.option_strings


@dataclass(frozen=True)
class CompletionCommand:
    """One top-level command and its parser-derived arguments."""

    name: str
    help: str
    arguments: tuple[CompletionArgument, ...]

    @property
    def positionals(self) -> tuple[CompletionArgument, ...]:
        return tuple(argument for argument in self.arguments if argument.positional)

    @property
    def options(self) -> tuple[CompletionArgument, ...]:
        return tuple(argument for argument in self.arguments if not argument.positional)


@dataclass(frozen=True)
class CompletionModel:
    """Complete completion metadata for the root parser."""

    program: str
    global_arguments: tuple[CompletionArgument, ...]
    commands: tuple[CompletionCommand, ...]

    @property
    def command_names(self) -> tuple[str, ...]:
        return tuple(command.name for command in self.commands)


def _clean_help(value: str | None) -> str:
    """Keep descriptions single-line and safe for every shell renderer."""

    return " ".join((value or "").split())


def _action_takes_value(action: argparse.Action) -> bool:
    """Return whether completion should consume a value after this action."""

    return action.nargs != 0 and not isinstance(
        action,
        (argparse._HelpAction, argparse._VersionAction),
    )


def _looks_like_file(action: argparse.Action) -> bool:
    """Infer path completion from parser names/help without duplicating CLI data."""

    haystack = " ".join(
        (
            action.dest,
            action.metavar or "",
            action.help or "",
        )
    ).lower()
    markers = (
        "file",
        "path",
        "vault",
        "output",
        "source json",
        "destination",
        "template",
        "report",
    )
    return any(marker in haystack for marker in markers)


def _argument_from_action(action: argparse.Action) -> CompletionArgument:
    choices = () if action.choices is None else tuple(str(choice) for choice in action.choices)
    return CompletionArgument(
        dest=action.dest,
        option_strings=tuple(action.option_strings),
        help=_clean_help(action.help),
        choices=choices,
        nargs="1" if action.nargs is None else str(action.nargs),
        required=bool(action.required),
        takes_value=_action_takes_value(action),
        file_completion=_looks_like_file(action),
    )


def parser_for_completions() -> argparse.ArgumentParser:
    """Build the CLI parser without initializing storage or other services."""

    from bookmark_organizer_pro.cli import BookmarkCLI

    return BookmarkCLI.__new__(BookmarkCLI)._build_parser()


def _subparsers(parser: argparse.ArgumentParser) -> argparse._SubParsersAction:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action
    raise ValueError("CLI parser has no subparser action")


def build_completion_model(parser: argparse.ArgumentParser | None = None) -> CompletionModel:
    """Project an argparse parser into shell-neutral completion metadata."""

    parser = parser or parser_for_completions()
    subparsers = _subparsers(parser)
    command_help = {
        action.dest: _clean_help(action.help)
        for action in subparsers._choices_actions
    }
    global_arguments = tuple(
        _argument_from_action(action)
        for action in parser._actions
        if not isinstance(action, argparse._SubParsersAction)
    )
    commands = tuple(
        CompletionCommand(
            name=name,
            help=command_help.get(name, ""),
            arguments=tuple(
                _argument_from_action(action)
                for action in command_parser._actions
            ),
        )
        for name, command_parser in subparsers.choices.items()
    )
    return CompletionModel(
        program=parser.prog.split()[-1] or "bop",
        global_arguments=global_arguments,
        commands=commands,
    )


def _shell_quote(value: str) -> str:
    """Quote a value for a Bash/Zsh shell literal."""

    return shlex.quote(str(value))


def _fish_quote(value: str) -> str:
    """Quote a value for a Fish double-quoted literal."""

    text = str(value)
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$") + '"'


def _option_strings(arguments: Iterable[CompletionArgument]) -> tuple[str, ...]:
    return tuple(
        option
        for argument in arguments
        for option in argument.option_strings
    )


def _bash_array(values: Iterable[str], indent: str = "        ") -> list[str]:
    values = tuple(values)
    if not values:
        return ["()"]
    return [
        "(",
        *(f"{indent}{_shell_quote(value)}" for value in values),
        indent[:-4] + ")",
    ]


def _array_assignment(
    declaration: str,
    values: Iterable[str],
    indent: str,
) -> list[str]:
    lines = _bash_array(values, indent=indent)
    lines[0] = declaration + lines[0]
    return lines


def _zsh_array(values: Iterable[str], indent: str = "        ") -> list[str]:
    values = tuple(values)
    if not values:
        return ["()"]
    return [
        "(",
        *(f"{indent}{_shell_quote(value)}" for value in values),
        indent[:-4] + ")",
    ]


def _choice_positionals(command: CompletionCommand) -> tuple[tuple[int, CompletionArgument], ...]:
    return tuple(
        (index, argument)
        for index, argument in enumerate(command.positionals)
        if argument.choices
    )


def _file_positionals(command: CompletionCommand) -> tuple[int, ...]:
    return tuple(
        index
        for index, argument in enumerate(command.positionals)
        if argument.file_completion
    )


def render_bash(model: CompletionModel) -> str:
    """Render a Bash completion function from a completion model."""

    lines = [
        "# Generated by scripts/generate_completions.py; do not edit.",
        "# bash completion for bop (Bookmark Organizer Pro)",
        "# Source this file: . bop.bash OR copy to /etc/bash_completion.d/",
        "",
        "_bop_complete_array() {",
        '    local cur="$1"',
        "    shift",
        "    COMPREPLY=()",
        "    local candidate",
        '    for candidate in "$@"; do',
        '        if [[ "$candidate" == "$cur"* ]]; then',
        '            COMPREPLY+=("$candidate")',
        "        fi",
        "    done",
        "}",
        "",
        "_bop_complete_files() {",
        '    mapfile -t COMPREPLY < <(compgen -f -- "$1")',
        "}",
        "",
        "_bop_completions() {",
        '    local cur="${COMP_WORDS[COMP_CWORD]}"',
        '    local prev=""',
        '    if (( COMP_CWORD > 0 )); then prev="${COMP_WORDS[COMP_CWORD-1]}"; fi',
        '    local cmd=""',
        '    if (( COMP_CWORD > 1 )); then cmd="${COMP_WORDS[1]}"; fi',
    ]
    lines.extend(_array_assignment("    local -a commands=", model.command_names, "        "))
    lines.extend(_array_assignment("    local -a global_options=", _option_strings(model.global_arguments), "        "))
    lines.extend(
        [
            "    if (( COMP_CWORD <= 1 )); then",
            '        _bop_complete_array "$cur" "${commands[@]}" "${global_options[@]}"',
            "        return 0",
            "    fi",
            "",
            '    case "$cmd" in',
        ]
    )

    for command in model.commands:
        lines.extend(
            [
                f"        {command.name})",
            ]
        )
        lines.extend(_array_assignment(
            "            local -a options=",
            _option_strings(command.arguments),
            "                ",
        ))
        lines.extend(
            [
                '            case "$prev" in',
            ]
        )
        for argument in command.options:
            if not argument.takes_value:
                continue
            for option in argument.option_strings:
                lines.append(f"                {option})")
                if argument.choices:
                    lines.extend(_array_assignment(
                        "                    local -a values=",
                        argument.choices,
                        "                        ",
                    ))
                    lines.extend(
                        [
                            '                    _bop_complete_array "$cur" "${values[@]}"',
                            "                    return 0",
                        ]
                    )
                elif argument.file_completion:
                    lines.extend(
                        [
                            '                    _bop_complete_files "$cur"',
                            "                    return 0",
                        ]
                    )
                lines.append("                    return 0")
                lines.append("                    ;;")
        lines.extend(
            [
                "            esac",
                '            if [[ "$cur" == -* ]]; then',
                '                _bop_complete_array "$cur" "${options[@]}"',
                "                return 0",
                "            fi",
            ]
        )
        for index, argument in _choice_positionals(command):
            lines.extend(
                [
                    f"            if (( COMP_CWORD == {index + 2} )); then",
                ]
            )
            lines.extend(_array_assignment(
                "                local -a values=",
                argument.choices,
                "                    ",
            ))
            lines.extend(
                [
                    '                _bop_complete_array "$cur" "${values[@]}"',
                    "                return 0",
                    "            fi",
                ]
            )
        for index in _file_positionals(command):
            lines.extend(
                [
                    f"            if (( COMP_CWORD == {index + 2} )); then",
                    '                _bop_complete_files "$cur"',
                    "                return 0",
                    "            fi",
                ]
            )
        lines.extend(
            [
                "            return 0",
                "            ;;",
            ]
        )

    lines.extend(
        [
            "    esac",
            "    return 0",
            "}",
            "",
            "complete -F _bop_completions bop",
            "",
        ]
    )
    return "\n".join(lines)


def _zsh_help(value: str) -> str:
    return value.replace("\\", "\\\\").replace("]", "\\]")


def _zsh_option_spec(argument: CompletionArgument, option: str) -> str:
    description = _zsh_help(argument.help)
    if not argument.takes_value:
        return f"{option}[{description}]"
    if argument.choices:
        choices = " ".join(_shell_quote(choice) for choice in argument.choices)
        return f"{option}[{description}]:{argument.dest}:({choices})"
    if argument.file_completion:
        return f"{option}[{description}]:{argument.dest}:_files"
    return f"{option}[{description}]:{argument.dest}:"


def render_zsh(model: CompletionModel) -> str:
    """Render a Zsh completion function from a completion model."""

    lines = [
        "#compdef bop",
        "# Generated by scripts/generate_completions.py; do not edit.",
        "# zsh completion for bop (Bookmark Organizer Pro)",
        "# Copy to a directory in your $fpath, e.g. ~/.zfunc/",
        "",
        "_bop() {",
    ]
    command_entries = [
        f"{command.name}:{command.help}" if command.help else command.name
        for command in model.commands
    ]
    command_entries.extend(
        f"{option}:{argument.help}" if argument.help else option
        for argument in model.global_arguments
        for option in argument.option_strings
    )
    lines.extend(_array_assignment("    local -a commands=", command_entries, "        "))
    lines.extend(
        [
            "    if (( CURRENT == 2 )); then",
            "        _describe 'command or option' commands",
            "        return",
            "    fi",
            "",
            '    case "$words[2]" in',
        ]
    )
    for command in model.commands:
        lines.append(f"        {command.name})")
        choice_positionals = _choice_positionals(command)
        file_positionals = _file_positionals(command)
        if choice_positionals or file_positionals:
            lines.extend(
                [
                    '            if [[ "$words[CURRENT]" != -* ]]; then',
                    "                case $CURRENT in",
                ]
            )
            for index, argument in choice_positionals:
                lines.extend(
                    [
                        f"                    {index + 2})",
                    ]
                )
                lines.extend(_array_assignment(
                    "                        local -a values=",
                    argument.choices,
                    "                            ",
                ))
                lines.extend(
                    [
                        "                        _describe 'argument' values",
                        "                        return",
                        "                        ;;",
                    ]
                )
            for index in file_positionals:
                lines.extend(
                    [
                        f"                    {index + 2})",
                        "                        _files",
                        "                        return",
                        "                        ;;",
                    ]
                )
            lines.extend(
                [
                    "                esac",
                    "            fi",
                ]
            )
        specs = [
            _zsh_option_spec(argument, option)
            for argument in command.options
            for option in argument.option_strings
        ]
        if specs:
            lines.append("            _arguments -s \\")
            for index, spec in enumerate(specs):
                line = f"                {_shell_quote(spec)}"
                if index < len(specs) - 1:
                    line += " " + chr(92)
                lines.append(line)
        lines.extend(
            [
                "            return",
                "            ;;",
            ]
        )
    lines.extend(
        [
            "    esac",
            "}",
            "",
            "_bop \"$@\"",
            "",
        ]
    )
    return "\n".join(lines)


def _fish_option_parts(option: str) -> tuple[str, str] | None:
    if option.startswith("--"):
        return "long", option[2:]
    if option.startswith("-") and len(option) == 2:
        return "short", option[1:]
    return None


def render_fish(model: CompletionModel) -> str:
    """Render Fish completion declarations from a completion model."""

    lines = [
        "# Generated by scripts/generate_completions.py; do not edit.",
        "# fish completion for bop (Bookmark Organizer Pro)",
        "# Copy to ~/.config/fish/completions/bop.fish",
        "",
        "set -l commands \\",
    ]
    continuation = chr(92)
    for index, command in enumerate(model.commands):
        suffix = f" {continuation}" if index < len(model.commands) - 1 else ""
        lines.append(f"    {_fish_quote(command.name)}{suffix}")
    lines.append("")
    root_condition = "not __fish_seen_subcommand_from " + " ".join(model.command_names)
    for command in model.commands:
        lines.append(
            "complete -c bop -f -n "
            f"{_fish_quote(root_condition)} -a {_fish_quote(command.name)}"
            f" -d {_fish_quote(command.help)}"
        )
    for argument in model.global_arguments:
        for option in argument.option_strings:
            parts = _fish_option_parts(option)
            if parts is None:
                continue
            option_kind, option_name = parts
            lines.append(
                "complete -c bop -n "
                f"{_fish_quote(root_condition)} -{option_kind[0]} {option_name}"
                f" -d {_fish_quote(argument.help)}"
            )
    for command in model.commands:
        condition = f"__fish_seen_subcommand_from {command.name}"
        for argument in command.options:
            for option in argument.option_strings:
                parts = _fish_option_parts(option)
                if parts is None:
                    continue
                option_kind, option_name = parts
                line = (
                    "complete -c bop -n "
                    f"{_fish_quote(condition)} -{option_kind[0]} {option_name}"
                    f" -d {_fish_quote(argument.help)}"
                )
                if argument.takes_value:
                    line += " -r"
                    for choice in argument.choices:
                        line += f" -a {_fish_quote(choice)}"
                lines.append(line)
        for _, argument in _choice_positionals(command):
            for choice in argument.choices:
                lines.append(
                    "complete -c bop -f -n "
                    f"{_fish_quote(condition)} -a {_fish_quote(choice)}"
                    f" -d {_fish_quote(argument.help)}"
                )
    lines.append("")
    return "\n".join(lines)


def render_completion_files(model: CompletionModel | None = None) -> dict[str, str]:
    """Return all checked-in completion files keyed by their file stem."""

    model = model or build_completion_model()
    return {
        "bop.bash": render_bash(model),
        "bop.zsh": render_zsh(model),
        "bop.fish": render_fish(model),
    }
