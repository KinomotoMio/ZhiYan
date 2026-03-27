from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

from app.services.generation.agentic.builder import AgentBuilder


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_smoke_real_model_uses_read_tool() -> None:
    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env", override=False)
    load_dotenv(project_root / ".env.local", override=False)

    model = os.getenv("AGENTLOOP_MODEL")
    if not model:
        pytest.skip("AGENTLOOP_MODEL is not configured.")

    builder = AgentBuilder.from_project(project_root)
    builder.with_litellm(
        model=model,
        api_base=os.getenv("AGENTLOOP_API_BASE"),
        api_key=os.getenv("AGENTLOOP_API_KEY"),
    )
    builder.discover_skills()
    builder.load_mcp_config()
    agent = builder.build()

    result = await agent.run("Use the read tool to read README.md and reply with only the first line.")

    assert result.stop_reason == "completed"
    assert "知演" in result.output_text
