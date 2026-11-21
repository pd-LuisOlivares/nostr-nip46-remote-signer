import asyncio
import os
import sys

from lab_real.signer import main

if __name__ == "__main__":
    code = 0
    try:
        code = asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterruptor de emergencia: sesion terminada, claves descartadas.", flush=True)
    os._exit(code)  # un input() pendiente en un hilo no debe retener el proceso
