"""Proxy de salida MINIMO con lista blanca de UN host:puerto (Fase 1.0A.2). Solo biblioteca estandar.

Acepta unicamente `CONNECT host:puerto` identico al permitido; todo lo demas recibe 403 SIN intentar conexion
alguna. No intercepta TLS (el firmante verifica el certificado del relay de extremo a extremo).
Registra solo host:puerto, motivo y bytes: nunca contenido.
"""
import asyncio
import os
import re
import time

from lab_common.log import emit

MAX_CONNS = 4
MAX_HEADER = 8192
CONNECT_TIMEOUT_S = 10
MAX_LIFETIME_S = 7200
HOST = re.compile(r"^(?=.{1,253}$)[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$")


def parse_connect(line: str):
    parts = line.split()
    if len(parts) != 3 or parts[0] != "CONNECT" or not parts[2].startswith("HTTP/1."):
        return None
    host, sep, port = parts[1].rpartition(":")
    if not sep or not host or not port.isdigit():
        return None
    return host.lower(), int(port)


def _clean(text: str) -> str:
    s = "".join(c if 32 <= ord(c) < 127 else "?" for c in text)
    return s[:80]


async def _respond(writer, status: str) -> None:
    writer.write(f"HTTP/1.1 {status}\r\nConnection: close\r\nContent-Length: 0\r\n\r\n".encode())
    try:
        await writer.drain()
    except ConnectionError:
        pass
    writer.close()


async def _pipe(reader, writer, counter: dict, key: str) -> None:
    try:
        while data := await reader.read(65536):
            counter[key] += len(data)
            writer.write(data)
            await writer.drain()
    except (ConnectionError, asyncio.CancelledError):
        pass
    finally:
        writer.close()


def parse_allow(allow: str) -> tuple[str, int]:
    """PROXY_ALLOW es EXACTAMENTE un `host:puerto`; listas, comodines, espacios o esquemas se rechazan al arrancar."""
    host, sep, port = allow.rpartition(":")
    if not (sep and HOST.match(host) and port.isdigit() and 1 <= int(port) <= 65535):
        raise ValueError("PROXY_ALLOW debe ser un unico host:puerto (sin listas, comodines, esquema ni espacios)")
    return host.lower(), int(port)


def build(host: str, port: int, allow: str):
    allowed = parse_allow(allow)
    state = {"active": 0}

    async def handler(reader, writer):
        try:
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 10)
        except asyncio.IncompleteReadError as exc:
            if not exc.partial:          # conexion cerrada sin enviar nada (p. ej. el healthcheck): sin registro ni respuesta
                writer.close()
                return
            emit(ev="connect_denied", reason="peticion incompleta o demasiado grande")
            await _respond(writer, "400 Bad Request")
            return
        except (asyncio.LimitOverrunError, asyncio.TimeoutError, ConnectionError):
            emit(ev="connect_denied", reason="peticion incompleta o demasiado grande")
            await _respond(writer, "400 Bad Request")
            return
        first = head.split(b"\r\n", 1)[0].decode("latin-1")
        target = parse_connect(first)
        if target is None:
            emit(ev="connect_denied", reason="no es CONNECT valido", linea=_clean(first))
            await _respond(writer, "403 Forbidden")
            return
        if target != allowed:
            emit(ev="connect_denied", reason="destino fuera de la lista blanca", target=_clean(f"{target[0]}:{target[1]}"))
            await _respond(writer, "403 Forbidden")
            return
        if state["active"] >= MAX_CONNS:
            emit(ev="connect_denied", reason="demasiadas conexiones", target=f"{target[0]}:{target[1]}")
            await _respond(writer, "503 Service Unavailable")
            return
        state["active"] += 1
        t0 = time.monotonic()
        counter = {"up": 0, "down": 0}
        try:
            try:
                up_r, up_w = await asyncio.wait_for(asyncio.open_connection(*target), CONNECT_TIMEOUT_S)
            except (OSError, asyncio.TimeoutError):
                emit(ev="connect_failed", target=f"{target[0]}:{target[1]}")
                await _respond(writer, "502 Bad Gateway")
                return
            emit(ev="connect_allowed", target=f"{target[0]}:{target[1]}")
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await writer.drain()
            try:
                await asyncio.wait_for(asyncio.gather(_pipe(reader, up_w, counter, "up"), _pipe(up_r, writer, counter, "down")), MAX_LIFETIME_S)
            except asyncio.TimeoutError:
                pass
            finally:
                up_w.close()
                writer.close()
            emit(ev="tunnel_closed", target=f"{target[0]}:{target[1]}", bytes_up=counter["up"], bytes_down=counter["down"],
                 seconds=round(time.monotonic() - t0, 1))
        finally:
            state["active"] -= 1

    return asyncio.start_server(handler, host, port, limit=MAX_HEADER)


async def run() -> None:
    allow = os.environ["PROXY_ALLOW"]  # unico host:puerto permitido
    port = int(os.environ.get("PROXY_PORT", "3128"))
    server = await build("0.0.0.0", port, allow)
    emit(ev="proxy_listening", port=port, allow=allow)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
