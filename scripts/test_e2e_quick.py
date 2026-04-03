#!/usr/bin/env python3
"""Quick e2e smoke test -- single event loop, no pytest overhead.

Usage::

    python scripts/test_e2e_quick.py            # Test DE (Tier 1)
    python scripts/test_e2e_quick.py --tier2    # Test SP (Tier 2 entry)
"""

import asyncio
import contextlib
import json
import sys
from pathlib import Path

# Ensure heddle is importable
BAFT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BAFT_DIR.parent / "heddle" / "src"))

from heddle.bus.nats_adapter import NATSBus
from heddle.mcp.bridge import BridgeTimeoutError, MCPBridge


async def test_tier1_de():
    """Tier 1: send a validate_only request to DE, check for response."""
    print("=" * 60)
    print("Tier 1 E2E: DE validate_only")
    print("=" * 60)

    bus = NATSBus("nats://localhost:4222")
    bridge = MCPBridge(bus)
    await bridge.connect()
    print("[OK] Connected to NATS")

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

    print("[..] Dispatching to de_database_engineer (tier=local, timeout=60s)...")

    try:
        result = await bridge.call_worker(
            worker_type="de_database_engineer",
            tier="local",
            payload=payload,
            timeout=60,
        )
        print("[OK] Got result!")
        status = result.status if hasattr(result, "status") else result.get("status", "unknown")
        output = result.output if hasattr(result, "output") else result.get("output", result)
        print(f"     Status: {status}")
        print(f"     Output: {json.dumps(output, indent=2, default=str)[:500]}")
        success = True
    except BridgeTimeoutError as e:
        print(f"[FAIL] Timeout: {e}")
        success = False
    except Exception as e:
        print(f"[FAIL] Error: {type(e).__name__}: {e}")
        success = False
    finally:
        with contextlib.suppress(Exception):
            await bus.close()

    return success


async def test_tier2_sp():
    """Tier 2: send a source_bundle to SP, check for extracted_claims."""
    print("=" * 60)
    print("Tier 2 E2E: SP source processing")
    print("=" * 60)

    bus = NATSBus("nats://localhost:4222")
    bridge = MCPBridge(bus)
    await bridge.connect()
    print("[OK] Connected to NATS")

    payload = {
        "source_bundle": {
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
        },
    }

    print("[..] Dispatching to sp_source_processor (tier=local, timeout=90s)...")

    try:
        result = await bridge.call_worker(
            worker_type="sp_source_processor",
            tier="local",
            payload=payload,
            timeout=90,
        )
        print("[OK] Got result!")
        status = result.status if hasattr(result, "status") else result.get("status", "unknown")
        output = result.output if hasattr(result, "output") else result.get("output", result)
        print(f"     Status: {status}")
        print(f"     Output: {json.dumps(output, indent=2, default=str)[:500]}")
        success = True
    except BridgeTimeoutError as e:
        print(f"[FAIL] Timeout: {e}")
        success = False
    except Exception as e:
        print(f"[FAIL] Error: {type(e).__name__}: {e}")
        success = False
    finally:
        with contextlib.suppress(Exception):
            await bus.close()

    return success


async def main() -> None:
    """Run Tier 1 and optionally Tier 2 smoke tests."""
    tier2 = "--tier2" in sys.argv

    ok = await test_tier1_de()

    if tier2:
        print()
        ok2 = await test_tier2_sp()
        ok = ok and ok2

    print()
    if ok:
        print("✅ All tests passed")
    else:
        print("❌ Some tests failed")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
