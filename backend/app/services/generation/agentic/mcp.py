from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class MCPServerCapabilities(BaseModel):
    tools: bool = False
    resources: bool = False
    prompts: bool = False


class MCPServerConfig(BaseModel):
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True
    transport: str = "stdio"
    capabilities: MCPServerCapabilities = Field(default_factory=MCPServerCapabilities)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MCPConfig(BaseModel):
    mcpServers: dict[str, MCPServerConfig] = Field(default_factory=dict)


@dataclass(slots=True)
class MCPDiagnostic:
    level: str
    message: str


@dataclass(slots=True)
class LoadedMCPConfig:
    path: Path
    config: MCPConfig
    diagnostics: list[MCPDiagnostic] = field(default_factory=list)


@dataclass(slots=True)
class MCPConfigLoader:
    project_root: Path
    relative_path: Path = Path(".agents/mcp.json")

    def load(self) -> LoadedMCPConfig:
        path = (self.project_root / self.relative_path).resolve()
        diagnostics: list[MCPDiagnostic] = []
        if not path.exists():
            diagnostics.append(MCPDiagnostic(level="warning", message=f"Missing MCP config: {path}"))
            return LoadedMCPConfig(path=path, config=MCPConfig(), diagnostics=diagnostics)
        payload = json.loads(path.read_text(encoding="utf-8"))
        config = MCPConfig.model_validate(payload)
        for name, server in config.mcpServers.items():
            if server.command is None:
                diagnostics.append(
                    MCPDiagnostic(level="warning", message=f"MCP server '{name}' has no command configured.")
                )
        return LoadedMCPConfig(path=path, config=config, diagnostics=diagnostics)

