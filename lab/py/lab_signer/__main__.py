import asyncio
import os

os.environ.setdefault("LAB_ACTOR", "signer-py")

from lab_signer.simulator import Signer  # noqa: E402

if __name__ == "__main__":
    try:
        asyncio.run(Signer().run())
    except KeyboardInterrupt:
        pass
