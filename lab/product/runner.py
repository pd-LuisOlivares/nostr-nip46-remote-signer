"""Ejecuta el firmante DEL PRODUCTO (`app.services`) contra el relay del laboratorio, para la regresión con el cliente NDK real.

Solo laboratorio: se niega a arrancar si el relay no es el del laboratorio (`ws://relay:7777`) o si el origen no termina en `.invalid`.
La aprobación del operador está AUTOMATIZADA aquí (única diferencia con el producto, que exige una decisión humana por la API): aprueba toda
solicitud que haya superado la política. No es un mecanismo del producto. Salida: líneas JSON con la auditoría (ya redactada) y las decisiones.
"""
import asyncio
import json
import os
import signal
import sys
from pathlib import Path

from app.config import Settings
from app.nostr.keys import Keypair
from app.services.runtime import SignerRuntime

CTL = Path("/ctl")


def emit(**fields: object) -> None:
    print(json.dumps({"actor": "product", **fields}, ensure_ascii=True, default=str), flush=True)


async def approver(runtime: SignerRuntime) -> None:
    seen: set[str] = set()
    while True:
        service = runtime.service
        for req in service.approvals.pending() if service else []:
            if req.id not in seen:
                seen.add(req.id)
                service.approvals.resolve(req.id, True)
                emit(ev="auto_approved", kind=req.kind.value, request_id=req.id, checks_ok=all(c["ok"] for c in req.checks))
        await asyncio.sleep(0.05)


async def main() -> int:
    settings = Settings.from_env(os.environ)
    if settings.relay_url != "ws://relay:7777" or not settings.service_origin.endswith(".invalid") or not settings.relay_allow_insecure:
        emit(ev="fatal", error="el arnes solo funciona con el relay y el origen del laboratorio")
        return 2
    runtime = SignerRuntime(settings, start_timeout_s=20)
    identity = Keypair.generate()
    runtime.set_identity(identity)
    stop = asyncio.Event()
    asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, stop.set)
    asyncio.get_running_loop().add_signal_handler(signal.SIGINT, stop.set)
    service = await runtime.start()
    CTL.joinpath("identity.txt").write_text(identity.public_hex, encoding="utf-8")
    CTL.joinpath("bunker.txt").write_text(service.issue_bunker_uri(), encoding="utf-8")  # solo canal tmpfs interno del laboratorio
    emit(ev="ready", state=service.state.value, transport_pub8=service.transport.public_hex[:8], identity_pub8=identity.public_hex[:8])
    task = asyncio.create_task(approver(runtime))
    waiter = asyncio.create_task(stop.wait())
    ended = asyncio.create_task(_until_ended(runtime))
    await asyncio.wait({waiter, ended}, return_when=asyncio.FIRST_COMPLETED)
    task.cancel()
    await runtime.shutdown()
    status = runtime.status()["signer"]
    for entry in runtime.audit.entries(500):
        emit(ev="audit", **entry)
    emit(ev="final", signatures=status["signatures"], state=status["state"], end_reason=status["end_reason"])
    return 0


async def _until_ended(runtime: SignerRuntime) -> None:
    while runtime.running:
        await asyncio.sleep(0.2)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
