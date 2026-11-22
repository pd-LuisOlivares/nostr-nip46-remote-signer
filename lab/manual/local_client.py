"""B6.1D: cliente NIP-46 de pruebas LOCAL para la demostración supervisada. Hace de «Stacker News» frente al relay local (nunca Internet).

Uso (desde la raíz del repositorio, con el entorno virtual activo):  python lab/manual/local_client.py [--relay ws://127.0.0.1:17777]

- Pide la URI `bunker://` con ENTRADA OCULTA (la copia la persona desde la interfaz) y la mantiene solo en memoria: no la imprime ni la guarda.
- Se conecta ÚNICAMENTE a un relay de loopback (127.0.0.1/localhost): rechaza cualquier otro destino.
- Imprime solo resultados saneados (prefijos de 8 caracteres, verdadero/falso, tiempos). Con `--evidence <archivo.json>` guarda ese mismo resumen.
- NO aprueba nada: cada `connect` y cada `sign_event` válido esperan la decisión HUMANA en el navegador. Las claves son efímeras y ficticias.
"""
import argparse
import getpass
import json
import queue
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from websockets.sync.client import connect  # noqa: E402

from app.nostr.event import NostrEvent, parse_and_verify_event, parse_event  # noqa: E402
from app.nostr.nip46 import Nip46Response, parse_bunker_uri  # noqa: E402
from tests.support import NdkLikeClient, login_template  # noqa: E402

ORIGIN = "https://sn.manual.invalid"
LOOPBACK = {"127.0.0.1", "localhost", "[::1]", "::1"}
SUMMARY: list[dict[str, object]] = []


def say(text: str) -> None:
    print(text, flush=True)


def record(step: str, ok: bool | None, **detail: object) -> None:
    SUMMARY.append({"paso": step, "resultado": "PASS" if ok else ("NO CONCLUYENTE" if ok is None else "FAIL"), **detail})
    say(f"  -> {'PASS' if ok else ('NO CONCLUYENTE' if ok is None else 'FALLA')}: {step}" + (f" {detail}" if detail else ""))


class Link:
    def __init__(self, relay_url: str, transport_pub: str) -> None:
        self.ndk = NdkLikeClient(transport_pub, time.time)
        self.ws = connect(relay_url, open_timeout=5)
        self.inbox: queue.Queue[NostrEvent] = queue.Queue()
        self.ws.send(json.dumps(["REQ", "c1", {"kinds": [24133], "#p": [self.ndk.key.public_hex], "since": int(time.time()) - 5}]))
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self) -> None:
        try:
            for raw in self.ws:
                msg = json.loads(raw)
                if msg[0] == "EVENT" and msg[1] == "c1":
                    self.inbox.put(parse_event(msg[2]))
        except Exception:  # noqa: BLE001 - se cierra al terminar
            return

    def send(self, method: str, params: list[str], **kw: object) -> float:
        self.ws.send(json.dumps(["EVENT", self.ndk.request(method, params, **kw)]))  # type: ignore[arg-type]
        return time.monotonic()

    def reply(self, timeout: float) -> Nip46Response | None:
        try:
            return self.ndk.decode(self.inbox.get(timeout=timeout))
        except queue.Empty:
            return None

    def quiet_for(self, seconds: float) -> bool:
        try:
            self.inbox.get(timeout=seconds)
        except queue.Empty:
            return True
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--relay", default="ws://127.0.0.1:17777", help="relay LOCAL publicado por Docker Compose en loopback")
    parser.add_argument("--evidence", help="archivo JSON donde guardar el resumen saneado")
    parser.add_argument("--wait", type=float, default=180.0, help="segundos máximos que espera cada decisión humana")
    args = parser.parse_args()

    host = urlsplit(args.relay).hostname or ""
    if urlsplit(args.relay).scheme != "ws" or host not in LOOPBACK:
        say("Rechazado: este cliente solo se conecta a un relay local (ws://127.0.0.1 o ws://localhost).")
        return 2
    uri = getpass.getpass("Pegue la URI bunker:// (no se muestra) y pulse Enter: ").strip()
    try:
        parsed = parse_bunker_uri(uri, allow_insecure_relays=True)
    except Exception:  # noqa: BLE001 - mensaje genérico, sin eco de la URI
        say("La URI no es válida.")
        return 2
    if not parsed.secret or any(urlsplit(r).hostname not in ("relay", *LOOPBACK) for r in parsed.relays):
        say("La URI no apunta al relay local de la demostración: se rechaza.")
        return 2
    signer_pub = parsed.signer_pubkey
    say(f"Clave de transporte del firmante: {signer_pub[:8]}…  (relay local: {args.relay})")
    link = Link(args.relay, signer_pub)

    # 1) connect (NIP-04, como NDK): exige APROBACIÓN HUMANA
    say("\n[1/6] connect → en el navegador aparece una solicitud «Conexión de un cliente». APRUÉBELA (tiene hasta %d s)." % args.wait)
    t0 = link.send("connect", ["", parsed.secret], scheme="nip04")
    resp = link.reply(args.wait)
    ok = resp is not None and resp.result == "ack"
    record("connect aprobado por una persona", ok, segundos_hasta_la_respuesta=round(time.monotonic() - t0, 1))
    if not ok:
        return 1

    # 2) get_public_key y ping
    link.send("get_public_key", [])
    resp = link.reply(10)
    identity_pub = resp.result if resp and resp.error is None else ""
    record("get_public_key devuelve la identidad (no la clave de transporte)", len(identity_pub) == 64 and identity_pub != signer_pub, identidad=identity_pub[:8] + "…")
    link.send("ping", [])
    resp = link.reply(10)
    record("ping", resp is not None and resp.result == "pong")

    # 3) solicitudes inválidas: se deniegan solas, sin llegar al operador
    say("\n[2/6] sign_event INVÁLIDO (origen ajeno y kind 1): debe rechazarse solo, SIN tarjeta pendiente en el navegador.")
    link.send("sign_event", [login_template(identity_pub, now=int(time.time()), origin="https://evil.example")])
    bad1 = link.reply(10)
    link.send("sign_event", [login_template(identity_pub, now=int(time.time()), origin=ORIGIN, kind=1)])
    bad2 = link.reply(10)
    record("sign_event inválido rechazado sin intervención del operador", bool(bad1 and bad2 and bad1.error == "unauthorized" and bad2.error == "unauthorized"))

    # 4) sign_event válido: NO debe firmar solo
    template = login_template(identity_pub, now=int(time.time()), origin=ORIGIN)
    template_id = json.loads(template)["id"]
    say("\n[3/6] sign_event VÁLIDO → aparece una tarjeta con 11 comprobaciones en verde. NO la apruebe todavía: espere a que este programa lo indique.")
    t1 = link.send("sign_event", [template])
    silent = link.quiet_for(8.0)
    record("ausencia de firma automática (8 s sin respuesta mientras nadie aprueba)", silent)
    if not silent:
        say("     (el firmante respondió antes de 8 s: sin aprobación humana no debería ocurrir)")
        return 1
    say("[4/6] AHORA apruebe la firma en el navegador (la ventana del firmante es de 30 s desde que se envió la solicitud: apruebe pronto).")
    resp = link.reply(args.wait)
    elapsed = round(time.monotonic() - t1, 1)
    signed_ok = False
    if resp is not None and resp.error is None and resp.result:
        try:
            event = parse_and_verify_event(json.loads(resp.result))
            signed_ok = event.pubkey == identity_pub and event.kind == 27235 and event.id == template_id
        except Exception:  # noqa: BLE001
            signed_ok = False
        record("sign_event aprobado: firma BIP-340 válida, de la identidad y sobre lo solicitado", signed_ok, segundos_desde_la_solicitud=elapsed)
    else:
        record("sign_event aprobado a tiempo", False, respuesta=(resp.error if resp else "sin respuesta"), segundos=elapsed)
        say("     Si tardó más de ~25 s, la revalidación (P-38) rechazó la firma y la interfaz debe decir «Rechazada al firmar». Vuelva a ejecutar este paso.")

    # 5) reutilización del mismo reto (solo tiene sentido si la firma anterior se realizó y gastó el reto)
    if signed_ok:
        link.send("sign_event", [template])
        replay = link.reply(10)
        record("reutilizar el mismo reto se rechaza sin preguntar", bool(replay and replay.error == "unauthorized"))

    # 6) aprobación tardía → revalidación P-38 (si se completó la firma válida)
    say("\n[5/6] PRUEBA DE APROBACIÓN TARDÍA (P-38/P-42): se envía otra solicitud válida. ESPERE a que el programa le indique y entonces aprúebela (después de ≥ 35 s).")
    late = login_template(identity_pub, now=int(time.time()), origin=ORIGIN, challenge="cd" * 32)
    t2 = link.send("sign_event", [late])
    for left in range(35, 0, -5):
        say(f"     … espere {left} s antes de aprobar")
        time.sleep(5)
    say("[6/6] YA puede aprobarla en el navegador (debe quedar «Rechazada al firmar: la política dejó de cumplirse», sin firma).")
    resp = link.reply(args.wait)
    record("aprobación tardía NO firma (revalidación)", bool(resp and resp.error == "unauthorized"), segundos=round(time.monotonic() - t2, 1))

    fails = [s for s in SUMMARY if s["resultado"] == "FAIL"]
    say(f"\nResumen: {len(SUMMARY) - len(fails)} de {len(SUMMARY)} comprobaciones PASS. (Sin URI, claves ni firmas en este resumen.)")
    if args.evidence:
        Path(args.evidence).write_text(json.dumps({"origen": ORIGIN, "relay": args.relay, "pasos": SUMMARY}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        say(f"Evidencia saneada guardada en {args.evidence}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
