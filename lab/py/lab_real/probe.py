"""Sonda de un relay (Fase 1.0A.2). Con un relay PUBLICO solo se ejecuta con autorizacion externa explicita.

Con una clave desechable en memoria: se suscribe, publica UN evento efimero (kind 24133, cifrado NIP-44 hacia si
misma) y comprueba el viaje de ida y vuelta. Mide EOSE, OK, eco, AUTH, avisos y latencias. No imprime claves ni
contenido. Con un relay real exige wss:// y proxy, igual que el firmante.
Uso: RELAY_URL=wss://... PROXY_URL=http://proxy:3128 python -m lab_real.probe
"""
import asyncio
import json
import os
import sys
import time
import urllib.parse

from websockets.asyncio.client import connect
from websockets.exceptions import WebSocketException

from lab_common import nip44, nostr
from lab_real.approval import LAB_HOSTS
from lab_real.policy import safe_text, sanitize
from lab_real.tls import ssl_kwargs


async def run_probe(relay_url: str, proxy_url: str | None, timeout_s: float = 10.0, tls_groups: str | None = None) -> dict:
    u = urllib.parse.urlsplit(relay_url)
    if (u.hostname or "") not in LAB_HOSTS and (u.scheme != "wss" or not proxy_url):
        raise ValueError("con un relay real la sonda exige wss:// y proxy")
    tls_kwargs = ssl_kwargs(tls_groups)
    sk = nostr.new_secret()
    pk = nostr.pubkey_of(sk)
    out = {"relay_host": u.hostname, "probe_pub8": pk[:8], "eose": False, "eose_ms": None, "ok": None, "ok_message": None,
           "ok_ms": None, "echo": False, "echo_ms": None, "auth_challenge_received": False, "notices": [], "tls_groups": tls_groups or "por_defecto"}
    t0 = time.monotonic()
    stage = {"now": "conexion"}   # conexion = proxy/TCP/TLS/handshake WebSocket; intercambio = ya con WSS abierto

    async def exchange():
        async with connect(relay_url, proxy=proxy_url, open_timeout=timeout_s, max_size=1 << 20, **tls_kwargs) as ws:
            stage["now"] = "intercambio"
            try:   # datos PUBLICOS del canal TLS (el contexto por defecto verifica certificado y nombre)
                so = ws.transport.get_extra_info("ssl_object")
                if so is not None:
                    cert = so.getpeercert() or {}
                    cn = lambda f: next((v for rdn in cert.get(f, ()) for k, v in rdn if k == "commonName"), None)  # noqa: E731
                    out["tls"] = {"version": so.version(), "cipher": so.cipher()[0], "verify_required": so.context.verify_mode.name,
                                  "check_hostname": so.context.check_hostname, "cert_subject_cn": cn("subject"),
                                  "cert_issuer_cn": cn("issuer"), "cert_not_after": cert.get("notAfter")}
            except (AttributeError, ValueError, TypeError) as exc:
                out["tls_info_error"] = type(exc).__name__
            await ws.send(json.dumps(["REQ", "probe", {"kinds": [24133], "#p": [pk]}]))
            ev = nostr.sign_event(sk, 24133, [["p", pk]], nip44.encrypt("lab-probe", nip44.get_conversation_key(sk, pk)), int(time.time()))
            sent = False
            async for raw in ws:
                msg = json.loads(raw)
                now = int((time.monotonic() - t0) * 1000)
                if msg[0] == "EOSE":
                    out["eose"], out["eose_ms"] = True, now
                    if not sent:
                        sent = True
                        await ws.send(json.dumps(["EVENT", ev]))
                        t_send = time.monotonic()
                elif msg[0] == "OK" and msg[1] == ev["id"]:
                    out["ok"], out["ok_message"], out["ok_ms"] = bool(msg[2]), sanitize(msg[3], 80), now
                elif msg[0] == "EVENT" and len(msg) == 3 and msg[2].get("id") == ev["id"]:
                    out["echo"], out["echo_ms"] = True, now
                    return
                elif msg[0] == "AUTH":   # condicion de aborto: se registra y se detiene SIN autenticarse ni publicar
                    out["auth_challenge_received"] = True
                    return
                elif msg[0] in ("NOTICE", "CLOSED"):
                    out["notices"].append(sanitize(msg[-1], 80))
                if out["ok"] is False:
                    return
            # el relay cerro el canal sin completar el intercambio
            out["error"], out["error_stage"], out["error_detail"] = "ConexionCerradaPorElRelay", "intercambio", "cierre limpio antes de completar"

    try:
        await asyncio.wait_for(exchange(), timeout_s * 2)
    except (OSError, asyncio.TimeoutError, json.JSONDecodeError, WebSocketException, IndexError, KeyError, TypeError, AttributeError) as exc:
        # OSError cubre TCP y TLS (ssl.SSLError); WebSocketException cubre InvalidProxyStatus, InvalidHandshake y ConnectionClosed;
        # los demas son mensajes del relay mal formados. El resultado SIEMPRE es un JSON estructurado.
        out["error"], out["error_stage"], out["error_detail"] = type(exc).__name__, stage["now"], safe_text(exc, 80)
    except Exception as exc:  # noqa: BLE001 - la sonda nunca termina con un traceback como unico resultado; se registra el tipo
        out["error"], out["error_stage"], out["error_detail"] = type(exc).__name__, stage["now"], "excepcion_no_prevista"
    out["verdict"] = "GO" if out["eose"] and out["ok"] and out["echo"] and not out["auth_challenge_received"] else "NO-GO"
    return out


if __name__ == "__main__":
    try:
        result = asyncio.run(run_probe(os.environ["RELAY_URL"], os.environ.get("PROXY_URL") or None, tls_groups=os.environ.get("TLS_GROUPS") or None))
    except (KeyError, ValueError) as exc:   # configuracion invalida: tambien JSON estructurado, y ninguna conexion
        result = {"verdict": "NO-GO", "error": "ConfiguracionInvalida", "error_stage": "configuracion",
                  "error_detail": "falta " + str(exc) if isinstance(exc, KeyError) else safe_text(exc, 80)}
        print(json.dumps(result, ensure_ascii=True))
        sys.exit(2)
    print(json.dumps(result, ensure_ascii=True))
    sys.exit(0 if result["verdict"] == "GO" else 1)
