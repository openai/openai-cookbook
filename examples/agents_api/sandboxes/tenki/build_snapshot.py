# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "tenki[async]>=1.4.1",
# ]
# ///

"""Build the golden image: a Tenki snapshot with the Codex CLI already installed."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from tenki import AsyncClient

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sandbox import INSTALL_EXECUTOR, INSTALL_STAMP

SNAPSHOT_NAME = "agents-api-codex"
# The builder's size is a floor on every restore, so build on the smallest
# machine a worker will ever use. Workers may be larger (see create_worker).
BUILDER_CORES = 1
BUILDER_MEMORY_MB = 1024


async def main() -> None:
    async with AsyncClient() as client:
        builder = await client.create(
            name=f"{SNAPSHOT_NAME}-builder",
            cpu_cores=BUILDER_CORES,
            memory_mb=BUILDER_MEMORY_MB,
            max_duration=900,
        )
        try:
            install = await builder.exec("sh", "-c", INSTALL_EXECUTOR, timeout=300)
            if install.exit_code != 0:
                raise RuntimeError(f"Install failed: {install.stderr_text.strip()}")
            version = await builder.exec("cat", INSTALL_STAMP)
            print(f"Installed: {version.stdout_text.strip()}", flush=True)
            # Flush writes before the disk is captured; the install left no services running.
            await builder.exec("sync")
            try:
                snapshot = await client.snapshots.create_and_wait(
                    builder.id, name=SNAPSHOT_NAME, timeout=600
                )
            except TimeoutError:
                # A gateway timeout can arrive while the capture still succeeds.
                # Reuse the newest snapshot with this name instead of building twice.
                candidates = [
                    s
                    for s in await client.snapshots.list()
                    if s.name == SNAPSHOT_NAME and s.session_id == builder.id
                ]
                if not candidates:
                    raise
                snapshot = await client.snapshots.wait_ready(
                    max(candidates, key=lambda s: s.created_at).id, timeout=600
                )
        finally:
            await builder.terminate()
    print(f"Snapshot: {snapshot.id} ({snapshot.state})")
    print(f"\nexport TENKI_SNAPSHOT_ID={snapshot.id}")


if __name__ == "__main__":
    asyncio.run(main())
