"""P-33: opera la aplicación COMPLETA (Uvicorn + FastAPI) por su API HTTP, dentro de la red interna del laboratorio.

Se ejecuta DENTRO del contenedor `app` (`docker compose exec`), solo con la biblioteca estándar, y habla con `127.0.0.1:8000`. Hace lo que haría el
operador: crea la identidad, inicia el firmante, emite la URI y decide cada solicitud llamando a `/approve` (aprobación por guion: SOLO en este arnés).
Credencial de operador: la variable de entorno que aporta el controlador (la lee del registro del contenedor). No imprime URI, claves ni credenciales.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8000"
HEADERS: dict[str, str] = {}
CTL = Path("/ctl")


def emit(**fields: object) -> None:
    print(json.dumps({"actor": "driver", **fields}, ensure_ascii=True, default=str), flush=True)


def call(method: str, path: str, body: object | None = None, *, ok: tuple[int, ...] = (200, 201)) -> object:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, method=method, headers={**HEADERS, **({"Content-Type": "application/json"} if data else {})})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            status, raw = resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        status, raw = exc.code, exc.read()
    if status not in ok:
        emit(ev="fatal", path=path, status=status)
        raise SystemExit(2)
    return json.loads(raw) if raw else None


def login() -> None:
    """Credencial de la API: ver `lab/product/auth_driver.py` (se sustituye al cambiar el mecanismo de autenticación)."""
    from auth_driver import authenticate  # noqa: PLC0415

    HEADERS.update(authenticate(BASE))


def main() -> int:
    login()
    ident = call("POST", "/api/identity")
    call("POST", "/api/signer/start")
    uri = call("POST", "/api/connections")["uri"]  # type: ignore[index]
    CTL.joinpath("identity.txt").write_text(ident["public_key"], encoding="utf-8")  # type: ignore[index]
    CTL.joinpath("bunker.txt").write_text(uri, encoding="utf-8")  # solo canal tmpfs interno del laboratorio
    emit(ev="ready")
    seen: set[str] = set()
    last_activity, started, approved_any = time.monotonic(), time.monotonic(), False
    while time.monotonic() - started < 100:
        for req in call("GET", "/api/requests"):  # type: ignore[attr-defined]
            if req["id"] not in seen:
                seen.add(req["id"])
                call("POST", f"/api/requests/{req['id']}/approve")
                emit(ev="auto_approved", kind=req["kind"], request_id=req["id"], checks_ok=all(c["ok"] for c in req["checks"]))
                approved_any, last_activity = True, time.monotonic()
        status = call("GET", "/api/status")["signer"]  # type: ignore[index]
        if status["state"] != "ready":
            break
        entries = call("GET", "/api/audit?limit=500")["entries"]  # type: ignore[index]
        if entries and entries[-1]["seq"] != getattr(main, "seq", None):
            main.seq = entries[-1]["seq"]  # type: ignore[attr-defined]
            last_activity = time.monotonic()
        if approved_any and time.monotonic() - last_activity > 6:
            break
        time.sleep(0.1)
    call("POST", "/api/signer/stop", ok=(200, 409))
    for entry in call("GET", "/api/audit?limit=500")["entries"]:  # type: ignore[index]
        emit(ev="audit", **entry)
    final = call("GET", "/api/status")["signer"]  # type: ignore[index]
    emit(ev="final", signatures=final["signatures"], state=final["state"], end_reason=final["end_reason"])
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    sys.exit(main())
