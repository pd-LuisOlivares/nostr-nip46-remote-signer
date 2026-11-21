"""Simulador MINIMO de firmante remoto NIP-46 para el laboratorio. NO es el firmante productivo.

Implementa solo lo que NDK 2.12.2 usa (connect, get_public_key, sign_event) mas ping, con
inyeccion de fallos para E7. Claves desechables generadas en memoria; nunca se registran.
Configuracion por entorno: REPLY_MODE (nip44|mirror|nip04), FAULT, JITTER_MS, USE_SECRET.
"""
import asyncio
import base64
import hashlib
import json
import os
import random
import time
import urllib.parse

from websockets.asyncio.client import connect

from lab_common import nip04, nip44, nostr
from lab_common.log import emit

RELAY_URL = os.environ.get("RELAY_URL", "ws://relay:7777")
REPLY_MODE = os.environ.get("REPLY_MODE", "nip44")
FAULT = os.environ.get("FAULT", "none")
JITTER_MS = int(os.environ.get("JITTER_MS", "0"))
USE_SECRET = os.environ.get("USE_SECRET", "1") == "1"
CTL = os.environ.get("CTL", "/ctl")
ACTOR = os.environ.get("LAB_ACTOR", "signer-py")
KIND_AUTH = 27235


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class Signer:
    def __init__(self):
        self.transport_sk = nostr.new_secret()   # clave de transporte (remote-signer-pubkey)
        self.identity_sk = nostr.new_secret()    # clave de identidad (user-pubkey), DISTINTA
        self.transport_pk = nostr.pubkey_of(self.transport_sk)
        self.identity_pk = nostr.pubkey_of(self.identity_sk)
        self.secret = base64.urlsafe_b64encode(os.urandom(16)).decode().rstrip("=") if USE_SECRET else None
        self.secret_used = False
        self.authorized: set[str] = set()
        self.seen: set[str] = set()
        self.mixed_counter = 0
        self.ws = None

    # ---- transporte ----
    async def publish(self, ev: dict, label: str, **info) -> None:
        if JITTER_MS:
            await asyncio.sleep(random.uniform(0, JITTER_MS) / 1000)
        await self.ws.send(json.dumps(["EVENT", ev], separators=(",", ":")))
        emit(ev="response_published", label=label, id=ev["id"][:16], author=ev["pubkey"][:8], **info)

    def encrypt_for(self, author_sk: bytes, client_pk: str, plaintext: str, scheme: str) -> str:
        if scheme == "nip04":
            return nip04.encrypt(author_sk, client_pk, plaintext)
        return nip44.encrypt(plaintext, nip44.get_conversation_key(author_sk, client_pk))

    def build_response(self, author_sk, client_pk, req_id, res, scheme, mutate=None, raw_content=None):
        body = {"id": req_id, "result": res.get("result", "")}
        if res.get("error"):
            body["error"] = res["error"]
        plaintext = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
        content = raw_content if raw_content is not None else self.encrypt_for(author_sk, client_pk, plaintext, scheme)
        if mutate:
            content = mutate(content)
        return nostr.sign_event(author_sk, 24133, [["p", client_pk]], content, int(time.time()))

    def scheme_for(self, request_scheme: str) -> str:
        if FAULT == "mixed":
            self.mixed_counter += 1
            return "nip44" if self.mixed_counter % 2 == 1 else "nip04"
        return request_scheme if REPLY_MODE == "mirror" else REPLY_MODE

    # ---- metodos NIP-46 ----
    def run_method(self, method: str, params: list, client_pk: str) -> dict:
        def err(msg):
            return {"result": "error", "error": msg}
        if method == "connect":
            if self.secret is not None:
                if self.secret_used or len(params) < 2 or params[1] != self.secret:
                    return err("unauthorized")
                self.secret_used = True
            self.authorized.add(client_pk)
            return {"result": "ack"}
        if client_pk not in self.authorized:
            return err("unauthorized")
        if method == "get_public_key":
            return {"result": self.identity_pk}
        if method == "ping":
            return {"result": "pong"}
        if method == "sign_event":
            try:
                tpl = json.loads(params[0])
                if tpl["kind"] != KIND_AUTH:
                    return err("unauthorized kind")
                if "pubkey" in tpl and tpl["pubkey"] != self.identity_pk:
                    return err("pubkey mismatch")
                signed = nostr.sign_event(self.identity_sk, tpl["kind"], tpl["tags"], tpl["content"], tpl["created_at"])
                if tpl.get("id") not in (None, signed["id"]):
                    emit(ev="client_id_mismatch", client_id=str(tpl.get("id"))[:16], own_id=signed["id"][:16])
                    return err("id mismatch")
                emit(ev="sign_event_ok", kind=signed["kind"], id=signed["id"][:16],
                     tags0=signed["tags"][0][0] if signed["tags"] else None)
                return {"result": json.dumps(signed, separators=(",", ":"), ensure_ascii=False)}
            except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
                return err("invalid params")
        return err("unsupported method")

    async def respond(self, client_pk, req_id, method, res, request_scheme):
        scheme = self.scheme_for(request_scheme)
        info = dict(method=method, scheme=scheme, fault=FAULT, req_id=req_id)
        ack = res.get("result") == "ack" and method == "connect"

        async def normal(label="normal", rid=None):
            ev = self.build_response(self.transport_sk, client_pk, rid or req_id, res, scheme)
            await self.publish(ev, label, **info)

        if method == "get_public_key" and FAULT == "get_pubkey_error":
            ev = self.build_response(self.transport_sk, client_pk, req_id, {"result": "", "error": "lab-error"}, scheme)
            await self.publish(ev, "get_pubkey_error", **info)
            return
        if not (ack and FAULT not in ("none", "mixed", "get_pubkey_error")):
            await normal()
            return
        if FAULT == "wrong_id":
            await normal("wrong_id", rid="wrong-" + os.urandom(4).hex())
            await asyncio.sleep(1.5)
            await normal("correct_after_wrong_id")
        elif FAULT == "error_field":
            ev = self.build_response(self.transport_sk, client_pk, req_id, {"result": "error", "error": "lab-denied"}, scheme)
            await self.publish(ev, "error_field", **info)
        elif FAULT == "malformed_json":
            ev = self.build_response(self.transport_sk, client_pk, req_id, res, scheme,
                                     raw_content=self.encrypt_for(self.transport_sk, client_pk, "not-json{", scheme))
            await self.publish(ev, "malformed_json", **info)
            await asyncio.sleep(1.5)
            await normal("correct_after_malformed")
        elif FAULT == "garbage":
            ev = self.build_response(self.transport_sk, client_pk, req_id, res, scheme,
                                     raw_content=base64.b64encode(os.urandom(120)).decode())
            await self.publish(ev, "garbage", **info)
            await asyncio.sleep(1.5)
            await normal("correct_after_garbage")
        elif FAULT == "bad_mac":
            def flip(content: str) -> str:
                raw = bytearray(base64.b64decode(content))
                raw[-1] ^= 0x01
                return base64.b64encode(bytes(raw)).decode()
            ev = self.build_response(self.transport_sk, client_pk, req_id, res, "nip44", mutate=flip)
            await self.publish(ev, "bad_mac", **info)
            await asyncio.sleep(1.5)
            await normal("correct_after_bad_mac")
        elif FAULT == "spoof":
            attacker = nostr.new_secret()
            ev = self.build_response(attacker, client_pk, req_id, res, scheme)
            await self.publish(ev, "spoofed_by_other_key", **info)
        elif FAULT == "duplicate":
            await normal("duplicate_1")
            await normal("duplicate_2")
        elif FAULT == "unknown_id_first":
            await normal("unknown_id", rid="unknown-" + os.urandom(4).hex())
            await normal("correct_after_unknown_id")
        elif FAULT == "auth_url":
            ev = self.build_response(self.transport_sk, client_pk, req_id,
                                     {"result": "auth_url", "error": "https://lab.invalid/approve"}, scheme)
            await self.publish(ev, "auth_url", **info)
            await asyncio.sleep(1.0)
            await normal("final_after_auth_url")
        else:
            await normal()

    async def handle_event(self, e: dict) -> None:
        ok, reason = nostr.verify_event(e)
        if not ok or e["kind"] != 24133 or ["p", self.transport_pk] not in [t[:2] for t in e["tags"]]:
            emit(ev="drop", reason=reason or "kind o etiqueta p incorrectos")
            return
        if e["id"] in self.seen:
            emit(ev="drop", reason="duplicado")
            return
        self.seen.add(e["id"])
        client_pk = e["pubkey"]
        scheme = "nip04" if "?iv=" in e["content"] else "nip44"
        try:
            if scheme == "nip04":
                plaintext = nip04.decrypt(self.transport_sk, client_pk, e["content"])
            else:
                plaintext = nip44.decrypt(e["content"], nip44.get_conversation_key(self.transport_sk, client_pk))
        except (nip04.Nip04Error, nip44.Nip44Error) as exc:
            emit(ev="decrypt_error", scheme=scheme, error=type(exc).__name__, client=client_pk[:8])
            return
        try:
            req = json.loads(plaintext)
            req_id, method, params = req["id"], req["method"], req.get("params", [])
        except (json.JSONDecodeError, KeyError, TypeError):
            emit(ev="request_malformed", scheme=scheme, plaintext_sha256=sha(plaintext))
            return
        emit(ev="request", method=method, scheme=scheme, req_id=req_id, client=client_pk[:8],
             plaintext_sha256=sha(plaintext), nparams=len(params))
        await self.respond(client_pk, req_id, method, self.run_method(method, params, client_pk), scheme)

    # ---- ciclo de vida ----
    async def run(self) -> None:
        async with connect(RELAY_URL, max_size=1 << 20) as ws:
            self.ws = ws
            await ws.send(json.dumps(["REQ", "s1", {"kinds": [24133], "#p": [self.transport_pk]}]))
            tasks = set()
            async for raw in ws:
                msg = json.loads(raw)
                if msg[0] == "EOSE" and msg[1] == "s1":
                    relay = urllib.parse.quote(RELAY_URL, safe="")
                    uri = f"bunker://{self.transport_pk}?relay={relay}" + (f"&secret={self.secret}" if self.secret else "")
                    with open(os.path.join(CTL, "identity.txt"), "w", encoding="utf-8") as fh:
                        fh.write(self.identity_pk)
                    with open(os.path.join(CTL, "bunker.txt"), "w", encoding="utf-8") as fh:
                        fh.write(uri)
                    emit(ev="ready", transport_pub8=self.transport_pk[:8], identity_pub8=self.identity_pk[:8],
                         transport_pub=self.transport_pk, identity_pub=self.identity_pk,
                         reply_mode=REPLY_MODE, fault=FAULT, jitter_ms=JITTER_MS, uses_secret=USE_SECRET)
                elif msg[0] == "EVENT":
                    t = asyncio.create_task(self.handle_event(msg[2]))
                    tasks.add(t)
                    t.add_done_callback(tasks.discard)
                elif msg[0] == "OK":
                    emit(ev="relay_ok", id=str(msg[1])[:16], accepted=msg[2], message=str(msg[3])[:60])
                elif msg[0] in ("CLOSED", "NOTICE"):
                    emit(ev="relay_notice", tipo=msg[0], message=str(msg[-1])[:80])
