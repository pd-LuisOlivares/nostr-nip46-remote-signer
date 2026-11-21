import asyncio
import os

os.environ.setdefault("LAB_ACTOR", "relay")

from lab_relay.server import run  # noqa: E402

if __name__ == "__main__":
    try:
        asyncio.run(run(port=int(os.environ.get("RELAY_PORT", "7777"))))
    except KeyboardInterrupt:
        pass
