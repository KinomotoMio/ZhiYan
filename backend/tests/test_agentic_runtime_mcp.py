from __future__ import annotations

import json
from pathlib import Path

from app.services.generation.agentic.mcp import MCPConfigLoader


def test_mcp_config_loader_parses_project_config(tmp_path: Path) -> None:
    config_dir = tmp_path / ".agents"
    config_dir.mkdir()
    (config_dir / "mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "filesystem": {
                        "command": "npx",
                        "args": ["@modelcontextprotocol/server-filesystem", "."],
                        "env": {"DEBUG": "1"},
                        "enabled": True,
                        "capabilities": {"tools": True, "resources": True, "prompts": False},
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    loaded = MCPConfigLoader(tmp_path).load()

    assert "filesystem" in loaded.config.mcpServers
    assert loaded.config.mcpServers["filesystem"].capabilities.resources is True

