"""First-time Telethon phone authentication helper.

Run this once after credentials are populated in ``~/.heddle/.env`` and
the Telegram account is unlocked. It walks the user through the
phone/code/2FA flow and persists a session file at
``$TELEGRAM_SESSION``.

Invoked from the CLI as ``baft itp-telegram auth``, but can also be run
directly for debugging::

    uv run python -m baft.itp_telegram.auth_bootstrap

After success, ``chmod 600 ~/.heddle/telegram.session`` so the session
file is treated like an SSH key.
"""

from __future__ import annotations

import asyncio
import logging
import os
import stat
import sys

from .config import ITPTelegramConfig

logger = logging.getLogger(__name__)


async def _auth_flow(cfg: ITPTelegramConfig) -> None:
    try:
        from telethon import TelegramClient
    except ImportError as exc:
        raise RuntimeError(
            "telethon is not installed. From the baft repo, run:\n"
            "    uv sync --extra telegram\n"
            "(or add `telegram` to baft's heddle-ai extras and re-sync.)"
        ) from exc

    cfg.ensure_credentials()
    cfg.ensure_dirs()

    client = TelegramClient(
        str(cfg.session_path),
        cfg.api_id,
        cfg.api_hash,
    )

    print(f"Connecting to Telegram with api_id={cfg.api_id}...")
    print(f"Session file: {cfg.session_path}")
    print()
    print("On first run, Telethon prompts interactively for your phone number,")
    print("the login code Telegram sends to your app, and (if enabled) your 2FA password.")
    print("Have your Telegram app open to receive the code.")
    print()

    async with client:
        me = await client.get_me()
        print()
        print(f"  OK: logged in as {me.first_name} (@{me.username}) id={me.id}")
        print()
        print("First 10 dialogs visible to this account:")
        async for dialog in client.iter_dialogs(limit=10):
            entity = dialog.entity
            entity_id = getattr(entity, "id", "?")
            print(f"  {entity_id:>15}  {dialog.name}")

    # Tighten permissions on the session file. Telethon writes 0644 by default.
    try:
        os.chmod(cfg.session_path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError as exc:
        logger.warning("Could not chmod session file %s: %s", cfg.session_path, exc)


def main() -> int:
    """CLI entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )
    cfg = ITPTelegramConfig.from_env()
    try:
        asyncio.run(_auth_flow(cfg))
    except Exception as exc:
        print(f"\n[FAIL] {exc}", file=sys.stderr)
        return 1
    print("\nNext: `baft itp-telegram resolve-ids` to convert handles to numeric IDs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
