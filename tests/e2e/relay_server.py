"""Relay Nostr mínimo SOLO para pruebas E2E (local, en memoria): REQ/EVENT/EOSE/OK con filtros `kinds`, `#p` y `since`. Uso: relay_server.py <puerto>."""
import asyncio
import json
import sys

from websockets.asyncio.server import ServerConnection, serve

EVENTS: list[dict[str, object]] = []
SUBS: dict[ServerConnection, dict[str, dict[str, object]]] = {}


def matches(event: dict[str, object], flt: dict[str, object]) -> bool:
    if "kinds" in flt and event.get("kind") not in flt["kinds"]:  # type: ignore[operator]
        return False
    if int(event.get("created_at", 0)) < int(flt.get("since", 0)):  # type: ignore[call-overload,arg-type]
        return False
    wanted = flt.get("#p")
    if wanted:
        tagged = {t[1] for t in event.get("tags", []) if len(t) > 1 and t[0] == "p"}  # type: ignore[union-attr]
        if not tagged & set(wanted):  # type: ignore[arg-type]
            return False
    return True


async def handler(ws: ServerConnection) -> None:
    SUBS[ws] = {}
    try:
        async for raw in ws:
            msg = json.loads(raw)
            if msg[0] == "REQ":
                SUBS[ws][msg[1]] = msg[2]
                for event in EVENTS:
                    if matches(event, msg[2]):
                        await ws.send(json.dumps(["EVENT", msg[1], event]))
                await ws.send(json.dumps(["EOSE", msg[1]]))
            elif msg[0] == "EVENT":
                event = msg[1]
                EVENTS.append(event)
                await ws.send(json.dumps(["OK", event["id"], True, ""]))
                for other, subs in list(SUBS.items()):
                    for sid, flt in subs.items():
                        if matches(event, flt):
                            await other.send(json.dumps(["EVENT", sid, event]))
            elif msg[0] == "CLOSE":
                SUBS[ws].pop(msg[1], None)
    finally:
        SUBS.pop(ws, None)


async def main(port: int) -> None:
    async with serve(handler, "127.0.0.1", port):
        print("relay listo", flush=True)
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1])))
