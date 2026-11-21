"""Firmante REAL MINIMO (laboratorio, Fase 1.0A.2). Solo atiende lo que NDK 2.12.2 usa: connect, get_public_key,
sign_event (+ ping). Claves desechables SOLO en memoria. Aprobacion humana por solicitud. Denegacion por defecto.

Diferencias deliberadas con lab_signer (simulador de E1-E7): sin motor de fallos, sin modo de respuesta configurable,
sin retardo aleatorio y sin archivo de control salvo en el ensayo local. Responde SIEMPRE en NIP-44 y acepta NIP-04
solo como entrada (hallazgos L-1/E3 de la Fase 1.0A.1).
"""
import asyncio
import base64
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.parse
from dataclasses import dataclass
from importlib import metadata

from websockets.asyncio.client import connect
from websockets.exceptions import WebSocketException

from lab_common import nip04, nip44, nostr
from lab_real import policy as pol
from lab_real.approval import LAB_HOSTS, decide, make_approver
from lab_real.evidence import HEX64, Evidence
from lab_real.tls import client_context, ssl_kwargs

MAX_SIGNATURES_HARD = 3
MAX_URIS_HARD = 3


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    relay_url: str
    origin: str
    proxy_url: str | None = None
    mode: str = "sign"                     # sign | observe (deniega siempre la firma; Ejecucion 0)
    approval_mode: str = "tty"             # tty | scripted (solo ensayo local)
    approval_script: str = ""
    approval_timeout_s: float = 120.0
    max_signatures: int = 2
    window_s: int = 120
    secret_ttl_s: int = 600
    connection_ttl_s: int = 1800
    session_ttl_s: int = 3600
    n_uris: int = 1
    relay_attempts: int = 3                # intentos de conexion al relay; la Compuerta B fija 1 (sin reintentos)
    max_requests: int = 60
    uri_file: str | None = None            # solo ensayo local: deja la URI en un tmpfs para el cliente de prueba
    evidence_path: str | None = "/results/evidence.jsonl"
    tls_groups: str | None = None          # p. ej. X25519: ClientHello pequeno (ver lab_real/tls.py); None = por defecto

    @property
    def relay_host(self) -> str:
        return urllib.parse.urlsplit(self.relay_url).hostname or ""

    @property
    def lab(self) -> bool:
        return self.relay_host in LAB_HOSTS

    def validate(self) -> "Config":
        if self.mode not in ("sign", "observe"):
            raise ConfigError("MODE debe ser sign u observe")
        if not (1 <= self.max_signatures <= MAX_SIGNATURES_HARD):
            raise ConfigError(f"MAX_SIGNATURES debe estar entre 1 y {MAX_SIGNATURES_HARD}")
        if not (1 <= self.relay_attempts <= 3):
            raise ConfigError("RELAY_ATTEMPTS debe estar entre 1 y 3")
        if not (1 <= self.n_uris <= MAX_URIS_HARD):
            raise ConfigError(f"N_URIS debe estar entre 1 y {MAX_URIS_HARD}")
        if not (1 <= self.window_s <= 300):
            raise ConfigError("WINDOW_S debe estar entre 1 y 300")
        pol.PolicyConfig(self.origin)  # valida SN_ORIGIN
        client_context(self.tls_groups)  # valida TLS_GROUPS (lanza ValueError)
        scheme = urllib.parse.urlsplit(self.relay_url).scheme
        if not self.lab:
            # Relay real: TLS obligatorio, proxy obligatorio, aprobacion en terminal, sin archivo de URI.
            if scheme != "wss":
                raise ConfigError("con un relay real la URL debe ser wss://")
            if not self.proxy_url:
                raise ConfigError("con un relay real el proxy de salida es obligatorio")
            if self.approval_mode != "tty":
                raise ConfigError("con un relay real la aprobacion debe ser humana (tty)")
            if self.uri_file:
                raise ConfigError("URI_FILE solo se permite con el relay del laboratorio")
        elif scheme not in ("ws", "wss"):
            raise ConfigError("RELAY_URL debe ser ws:// o wss://")
        return self

    @classmethod
    def from_env(cls, env=None) -> "Config":
        env = os.environ if env is None else env
        try:
            return cls(
                relay_url=env["RELAY_URL"], origin=env["SN_ORIGIN"], proxy_url=env.get("PROXY_URL") or None,
                mode=env.get("MODE", "observe"), approval_mode=env.get("APPROVAL_MODE", "tty"),
                approval_script=env.get("APPROVAL_SCRIPT", ""), approval_timeout_s=float(env.get("APPROVAL_TIMEOUT_S", "120")),
                max_signatures=int(env.get("MAX_SIGNATURES", "2")), window_s=int(env.get("WINDOW_S", "120")),
                secret_ttl_s=int(env.get("SECRET_TTL_S", "600")), connection_ttl_s=int(env.get("CONNECTION_TTL_S", "1800")),
                session_ttl_s=int(env.get("SESSION_TTL_S", "3600")), n_uris=int(env.get("N_URIS", "1")),
                max_requests=int(env.get("MAX_REQUESTS", "60")), relay_attempts=int(env.get("RELAY_ATTEMPTS", "3")), uri_file=env.get("URI_FILE") or None,
                evidence_path=env.get("EVIDENCE_PATH") or None, tls_groups=env.get("TLS_GROUPS") or None,
            ).validate()
        except KeyError as exc:
            raise ConfigError(f"falta la variable obligatoria {exc}") from exc
        except ValueError as exc:
            raise ConfigError(str(exc)) from exc


def say(text: str = "") -> None:
    print(text, flush=True)


def _sha16(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class Signer:
    def __init__(self, cfg: Config, evidence: Evidence, approver, clock=time.time):
        self.cfg, self.ev, self.approver, self.clock = cfg, evidence, approver, clock
        self.policy_cfg = pol.PolicyConfig(cfg.origin, window_s=cfg.window_s)
        self.transport_sk, self.identity_sk = nostr.new_secret(), nostr.new_secret()   # DISTINTAS; solo en memoria
        self.transport_pk, self.identity_pk = nostr.pubkey_of(self.transport_sk), nostr.pubkey_of(self.identity_sk)
        self.secrets: dict[str, dict] = {}        # sha256(secreto) -> {used, expires}; el secreto en claro no se guarda
        self.clients: dict[str, dict] = {}        # clave del cliente -> {state, expires}
        self.seen_events: set[str] = set()
        self.seen_requests: set[tuple] = set()
        self.seen_challenges: set[str] = set()
        self.signatures = 0
        self.requests = 0
        self.pending_ok: dict[str, str] = {}
        self.prompt_lock = asyncio.Lock()
        self.ws = None
        self.finished = False
        self.end_reason = "sin_motivo"
        self.issued = False
        self.deadline = self.clock() + cfg.session_ttl_s

    # ---------------------------------------------------------------- criptografia y transporte
    def _encrypt(self, client_pk: str, plaintext: str) -> str:
        return nip44.encrypt(plaintext, nip44.get_conversation_key(self.transport_sk, client_pk))

    async def _respond(self, client_pk: str, req_id: str, method: str, result: str, error: str | None = None) -> None:
        body = {"id": req_id, "result": result}
        if error:
            body["error"] = error
        content = self._encrypt(client_pk, json.dumps(body, separators=(",", ":"), ensure_ascii=False))
        out = nostr.sign_event(self.transport_sk, 24133, [["p", client_pk]], content, int(self.clock()))
        self.pending_ok[out["id"]] = method
        await self.ws.send(json.dumps(["EVENT", out], separators=(",", ":")))

    # ---------------------------------------------------------------- aprobacion
    async def _ask(self, kind: str, text: str):
        async with self.prompt_lock:   # nunca dos preguntas a la vez en la misma terminal
            return await decide(self.approver, kind, text, self.cfg.approval_timeout_s)

    # ---------------------------------------------------------------- metodos
    async def on_connect(self, client_pk: str, params: list):
        state = self.clients.get(client_pk)
        if state and state["state"] == "active":
            return "ack", None
        if state and state["state"] in ("pending", "denied"):
            return None, "unauthorized"
        provided = params[1] if len(params) >= 2 and isinstance(params[1], str) else ""
        digest = hashlib.sha256(provided.encode("utf-8")).hexdigest()
        match = None
        for known, meta in self.secrets.items():     # comparacion en tiempo constante, sin cortocircuito
            if hmac.compare_digest(known, digest) and not meta["used"] and meta["expires"] > self.clock():
                match = known
        if match is None:
            return None, "unauthorized"
        self.secrets[match]["used"] = True              # un solo uso, aunque se deniegue
        self.clients[client_pk] = {"state": "pending", "expires": 0}
        text = (f"\n=== SOLICITUD DE CONEXION ===\ncliente: {client_pk[:8]}...  (el secreto de la URI fue valido)\n"
                f"Activar esta conexion? [s/N]")
        approved, reason, ms = await self._ask("connect", text)
        self.ev.emit("decision", kind="connect", approved=approved, reason=reason, latency_ms=ms)
        if not approved:
            self.clients[client_pk]["state"] = "denied"
            return None, "unauthorized"
        self.clients[client_pk] = {"state": "active", "expires": self.clock() + self.cfg.connection_ttl_s}
        return "ack", None

    def _observe_sign(self, params) -> tuple:
        """Compuerta B: describe y DENIEGA. Es la primera ramificacion de on_sign: desde aqui no hay camino a `_ask` ni a la firma."""
        now = int(self.clock())
        desc = pol.describe_sign_params(params, now)
        failed = None
        if isinstance(params, list) and len(params) == 1 and isinstance(params[0], str):
            checks, _ = pol.evaluate(params[0], self.identity_pk, now, self.seen_challenges, self.policy_cfg)
            failed = pol.failed(checks)
        self.ev.emit("observed_sign", policy_failed=failed, **desc)
        self.ev.emit("decision", kind="sign_event", approved=False, reason="modo_observacion", latency_ms=0)
        say("\n=== SOLICITUD DE FIRMA RECIBIDA (MODO OBSERVACION: se deniega SIEMPRE) ===\n"
            + "\n".join(f"  {k}: {v}" for k, v in desc.items()) + f"\n  comprobaciones fallidas segun la politica: {failed}\n")
        return None, "unauthorized"

    async def on_sign(self, client_pk: str, params: list):
        if self.cfg.mode == "observe":
            return self._observe_sign(params)
        if self.signatures >= self.cfg.max_signatures:
            self.ev.emit("decision", kind="sign_event", approved=False, reason="tope", latency_ms=0)
            return None, "unauthorized"
        if not (isinstance(params, list) and len(params) == 1 and isinstance(params[0], str)):
            return None, "invalid params"
        raw = params[0]
        now = int(self.clock())
        checks, info = pol.evaluate(raw, self.identity_pk, now, self.seen_challenges, self.policy_cfg)
        ok = pol.all_ok(checks)
        origin_seen = info.get("origin_seen")
        if origin_seen and HEX64.search(origin_seen):   # `u` es texto no confiable: nunca se registra algo con forma de clave
            origin_seen = "<redactado>"
        self.ev.emit("policy", ok=ok, failed=pol.failed(checks), origin_seen=origin_seen,
                     content_ok=info.get("content_ok"), challenge_sha16=info.get("challenge_sha16"),
                     created_at_age_s=info.get("created_at_age_s"))
        lines = "\n".join(f"  [{'OK ' if c.ok else 'NO '}] {c.name:13} {c.detail if not c.ok else ''}" for c in checks)
        if not ok:
            say(f"\n=== EVENTO RECHAZADO POR LA POLITICA (no se ofrece aprobarlo) ===\n{lines}")
            return None, "unauthorized"
        tpl = json.loads(raw)
        summary = (f"\n=== SOLICITUD DE FIRMA ===\ncliente: {client_pk[:8]}...\nkind: {tpl['kind']}   "
                   f"created_at: {tpl['created_at']} ({info['created_at_age_s']} s de antiguedad)\n"
                   f"u (origen): {info['origin_seen']}\nchallenge: {tpl['tags'][0][1][:8]}...{tpl['tags'][0][1][-8:]} "
                   f"(sha {info['challenge_sha16']})\ncontent: {pol.sanitize(tpl['content'])}\ncomprobaciones:\n{lines}\n")
        approved, reason, ms = await self._ask("sign", summary + "Firmar UNA vez este evento? [s/N]")
        self.ev.emit("decision", kind="sign_event", approved=approved, reason=reason, latency_ms=ms)
        if not approved:
            return None, "unauthorized"
        # La aprobacion se consume de forma atomica ANTES de firmar (sin awaits entre la comprobacion y el consumo).
        chash = pol.challenge_hash(tpl["tags"][0][1])
        if chash in self.seen_challenges or self.signatures >= self.cfg.max_signatures:
            self.ev.emit("decision", kind="sign_event", approved=False, reason="reutilizacion_o_tope", latency_ms=0)
            return None, "unauthorized"
        self.seen_challenges.add(chash)
        self.signatures += 1
        signed = nostr.sign_event(self.identity_sk, tpl["kind"], tpl["tags"], tpl["content"], tpl["created_at"])
        verified, _ = nostr.verify_event(signed)
        unchanged = (signed["pubkey"] == self.identity_pk and signed["tags"] == tpl["tags"]
                     and signed["content"] == tpl["content"] and signed["created_at"] == tpl["created_at"]
                     and tpl.get("id") in (None, signed["id"]))
        self.ev.emit("sign_ok", event_id16=signed["id"][:16], tags0=signed["tags"][0][0], self_verify=bool(verified and unchanged))
        if not (verified and unchanged):
            return None, "internal error"
        return json.dumps(signed, separators=(",", ":"), ensure_ascii=False), None

    async def dispatch(self, client_pk: str, method: str, params: list):
        if method == "connect":
            return await self.on_connect(client_pk, params)
        state = self.clients.get(client_pk)
        if not state or state["state"] != "active" or state["expires"] <= self.clock():
            return None, "unauthorized"
        if method == "get_public_key":
            return self.identity_pk, None          # nunca error a un cliente activo (P-19)
        if method == "ping":
            return "pong", None
        if method == "sign_event":
            return await self.on_sign(client_pk, params)
        return None, "unsupported method"

    # ---------------------------------------------------------------- eventos de transporte
    async def handle_event(self, e: dict) -> None:
        ok, reason = nostr.verify_event(e)
        now = self.clock()
        if (not ok or e["kind"] != 24133 or ["p", self.transport_pk] not in [t[:2] for t in e["tags"]]
                or abs(now - e["created_at"]) > self.cfg.window_s or e["id"] in self.seen_events):
            self.ev.emit("error", where="transporte", error_type="evento_descartado")
            return
        self.seen_events.add(e["id"])
        self.requests += 1
        if self.requests > self.cfg.max_requests:
            self._end("tope_de_solicitudes")
            return
        client_pk = e["pubkey"]
        scheme = "nip04" if "?iv=" in e["content"] else "nip44"
        try:
            plaintext = (nip04.decrypt(self.transport_sk, client_pk, e["content"]) if scheme == "nip04"
                         else nip44.decrypt(e["content"], nip44.get_conversation_key(self.transport_sk, client_pk)))
            req = json.loads(plaintext)
            req_id, method = req["id"], req["method"]
            params = req.get("params", [])
            if not (isinstance(req_id, str) and len(req_id) <= 64 and isinstance(method, str) and isinstance(params, list)):
                raise ValueError("forma")
        except (nip04.Nip04Error, nip44.Nip44Error, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            self.ev.emit("error", where="solicitud", error_type=type(exc).__name__)   # no se distingue hacia el exterior
            return
        if (client_pk, req_id) in self.seen_requests:
            self.ev.emit("error", where="solicitud", error_type="id_repetido")
            return
        self.seen_requests.add((client_pk, req_id))
        self.ev.emit("request", method=pol.sanitize(method, 24), scheme=scheme, client8=client_pk[:8], plaintext_sha16=_sha16(plaintext))
        if self.cfg.mode == "observe":
            perms = params[2] if method == "connect" and len(params) >= 3 and isinstance(params[2], str) else None
            self.ev.emit("observed_request", method=pol.safe_text(method, 24), params_n=len(params),
                         param_types=[type(x).__name__ for x in params[:6]], perms_seen=pol.safe_text(perms, 60) if perms is not None else None)
        result, error = await self.dispatch(client_pk, method, params)
        await self._respond(client_pk, req_id, method if method in ("connect", "get_public_key", "ping", "sign_event") else "otro",
                            result or "error" if error else result, error)

    async def _guarded(self, e: dict) -> None:
        try:
            await self.handle_event(e)
        except Exception as exc:   # registra solo el tipo; una solicitud rota no debe tumbar la sesion
            self.ev.emit("error", where="manejador", error_type=type(exc).__name__)

    # ---------------------------------------------------------------- ciclo de vida
    def _end(self, reason: str) -> None:
        if not self.finished:
            self.finished, self.end_reason = True, reason

    def _issue_uris(self) -> None:
        relay = urllib.parse.quote(self.cfg.relay_url, safe="")
        uris = []
        for i in range(self.cfg.n_uris):
            secret = base64.urlsafe_b64encode(os.urandom(16)).decode().rstrip("=")      # 128 bits
            self.secrets[hashlib.sha256(secret.encode()).hexdigest()] = {"used": False, "expires": self.clock() + self.cfg.secret_ttl_s}
            uris.append(f"bunker://{self.transport_pk}?relay={relay}&secret={secret}")
            self.ev.emit("bunker_issued", transport_pub8=self.transport_pk[:8], ttl_s=self.cfg.secret_ttl_s, index=i + 1)
        if self.cfg.uri_file:                                   # solo ensayo local (guardado por Config.validate)
            d = os.path.dirname(self.cfg.uri_file)
            with open(os.path.join(d, "identity.txt"), "w", encoding="utf-8") as fh:
                fh.write(self.identity_pk)
            with open(self.cfg.uri_file, "w", encoding="utf-8") as fh:
                fh.write(uris[0])
        else:
            say("\n=== FIRMANTE LISTO ===  (cada URI es de UN solo uso y caduca; no se guarda en ningun archivo)")
            for i, u in enumerate(uris, 1):
                say(f"URI {i}: {u}")
            say(f"Identidad desechable (clave publica): {self.identity_pk[:8]}...  Esperando solicitudes. Ctrl+C = interruptor de emergencia.\n")
            if self.cfg.mode == "observe":
                say("MODO OBSERVACION (Compuerta B): ninguna firma es posible en este modo. Las solicitudes de firma se registran y se deniegan.\n")

    async def _session(self) -> None:
        async with connect(self.cfg.relay_url, proxy=self.cfg.proxy_url, open_timeout=15, max_size=1 << 20,
                                 **ssl_kwargs(self.cfg.tls_groups)) as ws:
            self.ws = ws
            await ws.send(json.dumps(["REQ", "s1", {"kinds": [24133], "#p": [self.transport_pk]}]))
            tasks: set = set()

            async def watchdog():
                while not self.finished:
                    await asyncio.sleep(1)
                    if self.clock() > self.deadline:
                        self._end("vida_maxima_de_sesion")
                await ws.close()

            wd = asyncio.create_task(watchdog())
            try:
                async for raw in ws:
                    msg = json.loads(raw)
                    if msg[0] == "EOSE" and msg[1] == "s1" and not self.issued:
                        self.issued = True
                        self.ev.emit("relay_ready")
                        self._issue_uris()
                    elif msg[0] == "EVENT" and len(msg) == 3 and isinstance(msg[2], dict):
                        t = asyncio.create_task(self._guarded(msg[2]))
                        tasks.add(t)
                        t.add_done_callback(tasks.discard)
                    elif msg[0] == "OK" and msg[1] in self.pending_ok:
                        self.ev.emit("response_published", method=self.pending_ok.pop(msg[1]), relay_ok=bool(msg[2]),
                                     relay_message=pol.sanitize(msg[3], 60))
                    if self.finished:
                        break
            finally:
                wd.cancel()

    async def run(self) -> str:
        versions = {}
        for name in ("websockets", "coincurve", "cryptography"):
            versions[name] = metadata.version(name)
        versions["python"] = sys.version.split()[0]
        cfg_sha = _sha16(json.dumps([self.cfg.origin, self.cfg.mode, self.cfg.max_signatures, self.cfg.window_s,
                                     self.cfg.secret_ttl_s, self.cfg.connection_ttl_s]))
        self.ev.emit("session_start", versions=versions, relay_host=self.cfg.relay_host, config_sha16=cfg_sha,
                     sn_origin=self.cfg.origin, mode=self.cfg.mode, max_signatures=self.cfg.max_signatures,
                     window_s=self.cfg.window_s, approval_mode=self.cfg.approval_mode)
        try:
            for attempt in range(self.cfg.relay_attempts):
                try:
                    await self._session()
                except (OSError, WebSocketException, asyncio.TimeoutError, json.JSONDecodeError) as exc:
                    self.ev.emit("error", where="relay", error_type=type(exc).__name__)
                if self.finished:
                    break
                if attempt + 1 < self.cfg.relay_attempts:
                    await asyncio.sleep(2)
            if not self.finished:
                self._end("relay_no_disponible")
        except asyncio.CancelledError:   # Ctrl+C: interruptor de emergencia
            self._end("interruptor_de_emergencia")
            raise
        finally:
            self.ev.emit("session_end", reason=self.end_reason, signatures=self.signatures)
        return self.end_reason


async def main() -> int:
    try:
        cfg = Config.from_env()
    except ConfigError as exc:
        print(f"CONFIGURACION INVALIDA: {exc}", file=sys.stderr)
        return 2
    signer = Signer(cfg, Evidence(cfg.evidence_path), make_approver(cfg.approval_mode, cfg.relay_host, cfg.approval_script))
    try:
        await signer.run()
    except asyncio.CancelledError:
        pass
    return 0
