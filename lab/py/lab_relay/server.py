"""Relay Nostr MINIMO para el laboratorio (subconjunto de NIP-01). No es un relay de produccion.

Implementa: EVENT, REQ, CLOSE (cliente) y EVENT, OK, EOSE, CLOSED, NOTICE (relay).
Filtros: ids, authors, kinds, #<letra>, since, until (limit se ignora: no hay almacenamiento).
NO implementa: persistencia, NIP-42, NIP-11, limites de tasa, autenticacion.
Coordinacion de carreras: el relay envia EOSE DESPUES de registrar la suscripcion, asi que todo
evento publicado despues del EOSE se entrega; el log 'sub_established' lo deja como evidencia.
"""
import asyncio
import collections
import itertools
import json
import re
from http import HTTPStatus

from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

from lab_common import nostr
from lab_common.log import emit

MAX_SUBS = 20
MAX_MESSAGE = 65536
DEDUP_SIZE = 10000
_ALLOWED_FILTER_KEYS = {"ids", "authors", "kinds", "since", "until", "limit"}
_NIP44_LIKE = re.compile(r"^A[g-v]")


def classify(content: str) -> str:
    if "?iv=" in content:
        return "nip04"
    return "nip44" if _NIP44_LIKE.match(content) else "otro"


def validate_filter(f) -> str | None:
    if not isinstance(f, dict):
        return "filtro no es un objeto"
    for key, val in f.items():
        if key in ("ids", "authors"):
            if not (isinstance(val, list) and val and all(isinstance(x, str) and re.fullmatch(r"[0-9a-f]{64}", x) for x in val)):
                return f"{key} invalido"
        elif key == "kinds":
            if not (isinstance(val, list) and all(isinstance(x, int) for x in val)):
                return "kinds invalido"
        elif key in ("since", "until", "limit"):
            if not isinstance(val, int):
                return f"{key} invalido"
        elif re.fullmatch(r"#[a-zA-Z]", key):
            if not (isinstance(val, list) and all(isinstance(x, str) for x in val)):
                return f"{key} invalido"
        else:
            return "unsupported: filter contains unknown elements"
    return None


def matches(f: dict, ev: dict) -> bool:
    if "ids" in f and ev["id"] not in f["ids"]:
        return False
    if "authors" in f and ev["pubkey"] not in f["authors"]:
        return False
    if "kinds" in f and ev["kind"] not in f["kinds"]:
        return False
    if "since" in f and ev["created_at"] < f["since"]:
        return False
    if "until" in f and ev["created_at"] > f["until"]:
        return False
    for key, vals in f.items():
        if re.fullmatch(r"#[a-zA-Z]", key):
            tagvals = {t[1] for t in ev["tags"] if len(t) >= 2 and t[0] == key[1]}
            if not tagvals.intersection(vals):
                return False
    return True


class Conn:
    def __init__(self, ws, cid: int):
        self.ws, self.cid, self.subs = ws, cid, {}


class Relay:
    def __init__(self):
        self.conns: dict[int, Conn] = {}
        self.seen: collections.OrderedDict[str, None] = collections.OrderedDict()
        self.counter = itertools.count(1)

    async def send(self, conn: Conn, msg: list) -> None:
        try:
            await conn.ws.send(json.dumps(msg, separators=(",", ":"), ensure_ascii=False))
        except ConnectionClosed:
            pass

    async def on_message(self, conn: Conn, raw) -> None:
        if isinstance(raw, bytes):
            await self.send(conn, ["NOTICE", "error: binary frames are not supported"])
            return
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            emit(ev="notice", conn=conn.cid, reason="json invalido")
            await self.send(conn, ["NOTICE", "error: invalid JSON"])
            return
        if not isinstance(msg, list) or not msg or not isinstance(msg[0], str):
            await self.send(conn, ["NOTICE", "error: message must be a JSON array"])
            return
        kind = msg[0]
        if kind == "EVENT" and len(msg) == 2:
            await self.on_event(conn, msg[1])
        elif kind == "REQ" and len(msg) >= 3:
            await self.on_req(conn, msg[1], msg[2:])
        elif kind == "CLOSE" and len(msg) == 2 and isinstance(msg[1], str):
            if conn.subs.pop(msg[1], None) is not None:
                emit(ev="sub_closed", conn=conn.cid, sub=msg[1])
        else:
            emit(ev="notice", conn=conn.cid, reason="mensaje no soportado", tipo=kind)
            await self.send(conn, ["NOTICE", "unsupported: unknown or malformed message"])

    async def on_event(self, conn: Conn, ev) -> None:
        eid = ev.get("id", "") if isinstance(ev, dict) and isinstance(ev.get("id"), str) else ""
        ok, reason = nostr.verify_event(ev)
        if not ok:
            emit(ev="event_rejected", conn=conn.cid, id=eid[:16], reason=reason)
            await self.send(conn, ["OK", eid, False, f"invalid: {reason}"])
            return
        if ev["id"] in self.seen:
            emit(ev="event_duplicate", conn=conn.cid, id=ev["id"][:16])
            await self.send(conn, ["OK", ev["id"], True, "duplicate: already have this event"])
            return
        self.seen[ev["id"]] = None
        if len(self.seen) > DEDUP_SIZE:
            self.seen.popitem(last=False)
        emit(ev="event_in", conn=conn.cid, id=ev["id"], kind=ev["kind"], author=ev["pubkey"][:8],
             p_tags=[t[1][:8] for t in ev["tags"] if len(t) >= 2 and t[0] == "p"],
             content_len=len(ev["content"]), scheme=classify(ev["content"]))
        await self.send(conn, ["OK", ev["id"], True, ""])
        for other in list(self.conns.values()):
            for sub_id, filters in list(other.subs.items()):
                if any(matches(f, ev) for f in filters):
                    emit(ev="event_out", conn=other.cid, sub=sub_id, id=ev["id"], kind=ev["kind"])
                    await self.send(other, ["EVENT", sub_id, ev])

    async def on_req(self, conn: Conn, sub_id, filters) -> None:
        if not (isinstance(sub_id, str) and 1 <= len(sub_id) <= 64):
            await self.send(conn, ["NOTICE", "error: invalid subscription id"])
            return
        for f in filters:
            problem = validate_filter(f)
            if problem:
                await self.send(conn, ["CLOSED", sub_id, problem if problem.startswith("unsupported") else f"invalid: {problem}"])
                return
        if sub_id not in conn.subs and len(conn.subs) >= MAX_SUBS:
            await self.send(conn, ["CLOSED", sub_id, "error: too many subscriptions"])
            return
        conn.subs[sub_id] = filters            # 1) registrar
        await self.send(conn, ["EOSE", sub_id])  # 2) confirmar: no hay eventos almacenados
        emit(ev="sub_established", conn=conn.cid, sub=sub_id, filters=filters)


def build(host: str, port: int):
    """Devuelve el gestor de contexto del servidor (port=0 elige un puerto libre; usado por las pruebas)."""
    relay = Relay()

    async def handler(ws):
        conn = Conn(ws, next(relay.counter))
        relay.conns[conn.cid] = conn
        emit(ev="conn_open", conn=conn.cid)
        try:
            async for raw in ws:
                await relay.on_message(conn, raw)
        except ConnectionClosed:
            pass
        finally:
            relay.conns.pop(conn.cid, None)
            emit(ev="conn_close", conn=conn.cid, subs_activas=len(conn.subs))

    def process_request(connection, request):
        if request.headers.get("Upgrade", "").lower() != "websocket":
            emit(ev="http_request", path=request.path, accept=request.headers.get("Accept", "")[:40])
            return connection.respond(HTTPStatus.NOT_FOUND, "no implementado en el relay de laboratorio\n")
        return None

    return serve(handler, host, port, max_size=MAX_MESSAGE, process_request=process_request,
                 ping_interval=None)


async def run(host: str = "0.0.0.0", port: int = 7777) -> None:
    async with build(host, port) as server:
        emit(ev="relay_listening", host=host, port=port)
        await server.serve_forever()
