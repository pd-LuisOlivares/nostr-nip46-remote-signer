"""Cliente de UNA vez para el ensayo E10b (no es una prueba unittest): usa la URI que recibe por argumento,
envia connect y get_public_key por el relay local e imprime un JSON con las respuestas. Claves desechables."""
import asyncio
import json
import sys
import time
import urllib.parse

from websockets.asyncio.client import connect

from lab_common import nip44, nostr


async def main(uri: str) -> dict:
    u = urllib.parse.urlsplit(uri.replace("bunker://", "http://", 1))
    tpk, q = u.hostname, urllib.parse.parse_qs(u.query)
    relay, secret = q["relay"][0], q["secret"][0]
    sk = nostr.new_secret()
    pk = nostr.pubkey_of(sk)
    key = nip44.get_conversation_key(sk, tpk)
    out: dict = {}

    async def rpc(ws, method, params, rid):
        ev = nostr.sign_event(sk, 24133, [["p", tpk]], nip44.encrypt(json.dumps({"id": rid, "method": method, "params": params}), key), int(time.time()))
        await ws.send(json.dumps(["EVENT", ev]))
        async for raw in ws:
            msg = json.loads(raw)
            if msg[0] == "EVENT" and msg[2]["pubkey"] == tpk:
                body = json.loads(nip44.decrypt(msg[2]["content"], key))
                if body.get("id") == rid:
                    return body.get("error") or body.get("result")

    async with connect(relay, open_timeout=10) as ws:
        await ws.send(json.dumps(["REQ", "c", {"kinds": [24133], "#p": [pk]}]))
        out["connect"] = await asyncio.wait_for(rpc(ws, "connect", [tpk, secret], "c1"), 40)
        out["get_public_key"] = await asyncio.wait_for(rpc(ws, "get_public_key", [], "c2"), 10)
    return out


if __name__ == "__main__":
    print(json.dumps(asyncio.run(main(sys.argv[1]))), flush=True)
    sys.exit(0)
