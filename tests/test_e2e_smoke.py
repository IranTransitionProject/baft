"""
test_e2e_smoke.py
-----------------
End-to-end smoke tests for Tier 1 and Tier 2 pipelines.

These tests require live infrastructure (NATS, workers running).
Run with: pytest tests/test_e2e_smoke.py -v -m e2e

Skip conditions:
  - NATS not reachable at localhost:4222
  - Heddle workers not running
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
import pytest_asyncio

BAFT_ROOT = Path(__file__).parent.parent

# Mark all tests in this module as e2e (skip by default)
pytestmark = pytest.mark.e2e


def _nats_available() -> bool:
    """Check if NATS is reachable."""
    try:
        import nats

        async def _check():
            nc = await nats.connect("nats://localhost:4222")
            await nc.close()
            return True

        return asyncio.run(_check())
    except Exception:
        return False


skip_no_nats = pytest.mark.skipif(
    not _nats_available(),
    reason="NATS not available at localhost:4222",
)


@pytest_asyncio.fixture
async def bridge():
    """Shared async bridge fixture — single event loop for connect/test/teardown."""
    from heddle.bus.nats_adapter import NATSBus
    from heddle.mcp.bridge import MCPBridge

    bus = NATSBus("nats://localhost:4222")
    br = MCPBridge(bus)
    await br.connect()
    yield br
    try:
        await bus.close()
    except Exception:
        pass


@skip_no_nats
class TestTier1Smoke:
    """Tier 1: Direct DE worker validation (single worker, no pipeline)."""

    @pytest.mark.asyncio
    async def test_de_validate_only(self, bridge):
        """Submit a validate-only request to DE and check for valid response."""
        payload = {
            "integration_request": {
                "session_id": "e2e_test",
                "operations": [
                    {
                        "action": "validate_only",
                        "target_file": "data/variables.yaml",
                    }
                ],
            },
        }

        result = await bridge.call_worker(
            worker_type="de_database_engineer",
            tier="local",
            payload=payload,
            timeout=30,
        )
        assert isinstance(result, dict)
        # DE should return an integration_result
        assert "integration_result" in result or "validation_result" in result


@skip_no_nats
class TestTier2Smoke:
    """Tier 2: SP → IA → XV → DE pipeline via source_bundle."""

    @pytest.mark.asyncio
    async def test_sp_processes_source_bundle(self, bridge):
        """Submit a minimal source_bundle to SP and check for extracted_claims."""
        source_bundle = {
            "type": "source_bundle",
            "items": [
                {
                    "url": "https://example.com/test",
                    "language": "en",
                    "source_tier": 3,
                    "retrieval_date": "2026-03-15",
                    "raw_text": (
                        "Iranian state media reported that IRGC commanders met with "
                        "Larijani to discuss succession arrangements following the "
                        "February strikes. The meeting took place at a secure "
                        "location in Tehran on March 10, 2026."
                    ),
                }
            ],
        }

        result = await bridge.call_worker(
            worker_type="sp_source_processor",
            tier="local",
            payload={"source_bundle": source_bundle},
            timeout=60,
        )
        assert isinstance(result, dict)
        # SP should return extracted_claims
        assert "extracted_claims" in result


@skip_no_nats
class TestMCPServerStarts:
    """MCP server must start and list tools."""

    @pytest.mark.asyncio
    async def test_create_server_with_itp_config(self):
        """create_server succeeds with the ITP MCP config."""
        from heddle.mcp.server import create_server

        server, gateway = create_server(str(BAFT_ROOT / "configs" / "mcp" / "itp.yaml"))
        assert gateway.config["name"] == "baft"
        assert len(gateway.tool_registry) > 0


class TestMCPServerCreation:
    """Non-e2e: MCP server creation (no NATS needed for this)."""

    def test_create_server_discovers_tools(self):
        """create_server should discover query tools even without NATS."""
        from heddle.mcp.server import create_server

        server, gateway = create_server(str(BAFT_ROOT / "configs" / "mcp" / "itp.yaml"))
        tool_names = sorted(gateway.tool_registry.keys())
        # Query tools should always be discovered (don't need NATS)
        query_tools = [t for t in tool_names if t.startswith("itp_")]
        assert len(query_tools) >= 4, f"Expected at least 4 itp_* query tools, found: {query_tools}"
