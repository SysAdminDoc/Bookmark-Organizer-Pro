# Roadmap — Bookmark Organizer Pro

Actionable work only. Historical and completed roadmap material is archived in CHANGELOG.md; blocked work is kept in Roadmap_Blocked.md.

## Actionable Items

- [ ] P3 — R-119: Declare the MCP server's launchable entry point in server.json
  Why: `packaging/server.json` names the PyPI package `bookmark-organizer-pro`, but the console scripts are `bop` and `bop-mcp`, so a registry consumer running `uvx bookmark-organizer-pro` has nothing to execute; the registry schema offers `runtimeArguments`/`packageArguments` for this but their Argument shape was not verified during R-116.
  Evidence: `packaging/server.json` (`runtimeHint: uvx`, no arguments); `pyproject.toml` `[project.scripts]` (`bop`, `bop-mcp`); https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json.
  Touches: `packaging/server.json`, `scripts/package_contract_audit.py::validate_mcp_server_json`, `tests/test_packaging.py`.
  Acceptance: `server.json` declares arguments that resolve to the `bop-mcp` stdio entry point, validated against the published Argument schema; the audit asserts the declared entry point matches a real `[project.scripts]` name; a consumer command is documented in the README MCP section.
  Complexity: S
