"""Checks that the Claude Code plugin wrapper stays in step with the server.

The repo doubles as a plugin: `.mcp.json` launches this package and the
skills in `skills/` tell the model which tools to call. Both drift silently
when a tool or entry point is renamed, so these tests pin them.
"""

import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL_FILES = sorted((ROOT / "skills").rglob("*.md"))
# Backticked calls such as `copy_scheduling(target_card_ids, …)`.
TOOL_CALL = re.compile(r"`([a-z][a-z_]+)\(")
# Backticked words in the tool table, e.g. `list_tags`.
BACKTICKED_WORD = re.compile(r"`([a-z]+(?:_[a-z]+)+)`")


async def _tool_names() -> set[str]:
    import mcp_ankiconnect.main  # noqa: F401  # registers every tool module
    from mcp_ankiconnect.server import mcp

    return {t.name for t in await mcp.list_tools()}


async def test_skills_only_call_registered_tools():
    tools = await _tool_names()
    unknown = {
        f"{path.relative_to(ROOT)}: {name}"
        for path in SKILL_FILES
        for name in TOOL_CALL.findall(path.read_text())
        if name not in tools
    }
    assert unknown == set()


async def test_card_writing_tool_table_names_real_tools():
    tools = await _tool_names()
    table = (ROOT / "skills/card-writing/SKILL.md").read_text().split("## 2.")[0]
    not_tools = {"note_ids", "best_performance"}  # an argument and a value
    named = set(BACKTICKED_WORD.findall(table)) - not_tools
    assert named - tools == set()


def test_mcp_json_launches_the_package_entry_point():
    scripts = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["scripts"]
    server = json.loads((ROOT / ".mcp.json").read_text())["mcpServers"]["ankiconnect"]
    assert server["args"][-1] in scripts
    assert "${CLAUDE_PLUGIN_ROOT}" in server["args"]
    # config.py reads this variable; a rename would silently fall back to 8765.
    assert "ANKI_CONNECT_URL" in server["env"]


def test_plugin_version_matches_package():
    package = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    plugin = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())
    assert plugin["version"] == package["version"]
