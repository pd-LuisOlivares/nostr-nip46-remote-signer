"""Pruebas del relay minimo (unittest). El relay corre en proceso, en loopback, con puerto efimero."""
import asyncio
import json
import os
import time
import unittest

os.environ["LAB_QUIET"] = "1"

from websockets.asyncio.client import connect  # noqa: E402
from websockets.exceptions import ConnectionClosed  # noqa: E402

from lab_common import nostr  # noqa: E402
from lab_relay.server import MAX_SUBS, build  # noqa: E402

TARGET = nostr.pubkey_of(nostr.new_secret())


def make_event(secret=None, kind=24133, p=TARGET, content="hola", created_at=None, extra_tags=()):
    secret = secret or nostr.new_secret()
    tags = [["p", p]] + [list(t) for t in extra_tags]
    return nostr.sign_event(secret, kind, tags, content, created_at or int(time.time()))


class RelayCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.cm = build("127.0.0.1", 0)
        self.server = await self.cm.__aenter__()
        self.port = self.server.sockets[0].getsockname()[1]
        self.clients = []

    async def asyncTearDown(self):
        for c in self.clients:
            await c.close()
        await self.cm.__aexit__(None, None, None)

    async def client(self):
        ws = await connect(f"ws://127.0.0.1:{self.port}")
        self.clients.append(ws)
        return ws

    async def recv(self, ws, timeout=2.0):
        return json.loads(await asyncio.wait_for(ws.recv(), timeout))

    async def expect_silence(self, ws, timeout=0.4):
        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(ws.recv(), timeout)

    async def subscribe(self, ws, sub, *filters):
        await ws.send(json.dumps(["REQ", sub, *filters]))
        self.assertEqual(await self.recv(ws), ["EOSE", sub])

    async def publish(self, ws, ev):
        await ws.send(json.dumps(["EVENT", ev]))
        return await self.recv(ws)

    # --- suscripcion y confirmacion ---
    async def test_subscription_is_confirmed_with_eose(self):
        ws = await self.client()
        await self.subscribe(ws, "s1", {"kinds": [24133], "#p": [TARGET]})

    # --- publicacion y OK ---
    async def test_publish_returns_ok_true(self):
        ws = await self.client()
        ev = make_event()
        self.assertEqual(await self.publish(ws, ev), ["OK", ev["id"], True, ""])

    # --- entrega a suscriptores correspondientes ---
    async def test_event_is_delivered_to_matching_subscriber_only(self):
        pub, sub_match, sub_other = await self.client(), await self.client(), await self.client()
        await self.subscribe(sub_match, "a", {"kinds": [24133], "#p": [TARGET]})
        await self.subscribe(sub_other, "b", {"kinds": [24133], "#p": ["f" * 64]})
        ev = make_event()
        await self.publish(pub, ev)
        self.assertEqual(await self.recv(sub_match), ["EVENT", "a", ev])
        await self.expect_silence(sub_other)

    async def test_sender_with_matching_subscription_receives_its_own_event(self):
        ws = await self.client()
        await self.subscribe(ws, "self", {"kinds": [24133]})
        ev = make_event()
        await ws.send(json.dumps(["EVENT", ev]))
        got = [await self.recv(ws), await self.recv(ws)]
        self.assertIn(["OK", ev["id"], True, ""], got)
        self.assertIn(["EVENT", "self", ev], got)

    # --- filtros ---
    async def test_filters_kinds_authors_ids_tags_since_until(self):
        pub, sub = await self.client(), await self.client()
        secret = nostr.new_secret()
        author = nostr.pubkey_of(secret)
        now = int(time.time())
        target = make_event(secret=secret, created_at=now)
        cases = {
            "kinds": {"kinds": [1]},
            "authors": {"authors": ["a" * 64]},
            "ids": {"ids": ["b" * 64]},
            "#p": {"#p": ["c" * 64]},
            "since": {"since": now + 100},
            "until": {"until": now - 100},
        }
        for name, f in cases.items():
            await self.subscribe(sub, f"neg-{name}", f)
        await self.subscribe(sub, "pos", {"kinds": [24133], "authors": [author], "ids": [target["id"]],
                                          "#p": [TARGET], "since": now - 5, "until": now + 5})
        await self.publish(pub, target)
        self.assertEqual(await self.recv(sub), ["EVENT", "pos", target])
        await self.expect_silence(sub)  # ninguna suscripcion negativa recibe nada

    async def test_unknown_filter_key_is_closed(self):
        ws = await self.client()
        await ws.send(json.dumps(["REQ", "x", {"bogus": [1]}]))
        msg = await self.recv(ws)
        self.assertEqual(msg[0:2], ["CLOSED", "x"])
        self.assertTrue(msg[2].startswith("unsupported"))

    # --- rechazo de eventos invalidos ---
    async def test_event_with_tampered_content_is_rejected(self):
        ws = await self.client()
        ev = make_event()
        ev["content"] = "otro"
        reply = await self.publish(ws, ev)
        self.assertEqual(reply[0:3], ["OK", ev["id"], False])
        self.assertTrue(reply[3].startswith("invalid:"))

    async def test_event_with_bad_signature_is_rejected(self):
        ws = await self.client()
        ev = make_event()
        ev["sig"] = ("0" if ev["sig"][0] != "0" else "1") + ev["sig"][1:]
        reply = await self.publish(ws, ev)
        self.assertFalse(reply[2])
        self.assertTrue(reply[3].startswith("invalid:"))

    async def test_invalid_event_is_not_delivered(self):
        pub, sub = await self.client(), await self.client()
        await self.subscribe(sub, "s", {"kinds": [24133]})
        ev = make_event()
        ev["content"] = "manipulado"
        await self.publish(pub, ev)
        await self.expect_silence(sub)

    async def test_malformed_inputs_get_notice(self):
        ws = await self.client()
        for raw in ("no es json", json.dumps({"a": 1}), json.dumps(["DESCONOCIDO", 1])):
            await ws.send(raw)
            self.assertEqual((await self.recv(ws))[0], "NOTICE")

    # --- duplicados ---
    async def test_duplicate_is_acknowledged_but_not_redelivered(self):
        pub, sub = await self.client(), await self.client()
        await self.subscribe(sub, "s", {"kinds": [24133]})
        ev = make_event()
        await self.publish(pub, ev)
        self.assertEqual((await self.recv(sub))[0], "EVENT")
        reply = await self.publish(pub, ev)
        self.assertEqual(reply[0:3], ["OK", ev["id"], True])
        self.assertTrue(reply[3].startswith("duplicate:"))
        await self.expect_silence(sub)

    # --- cierre de suscripciones ---
    async def test_close_stops_delivery(self):
        pub, sub = await self.client(), await self.client()
        await self.subscribe(sub, "s", {"kinds": [24133]})
        await sub.send(json.dumps(["CLOSE", "s"]))
        await asyncio.sleep(0.1)
        await self.publish(pub, make_event())
        await self.expect_silence(sub)

    # --- desconexion y limpieza ---
    async def test_disconnect_does_not_break_delivery_to_others(self):
        pub, gone, stay = await self.client(), await self.client(), await self.client()
        await self.subscribe(gone, "g", {"kinds": [24133]})
        await self.subscribe(stay, "k", {"kinds": [24133]})
        await gone.close()
        await asyncio.sleep(0.1)
        ev = make_event()
        await self.publish(pub, ev)
        self.assertEqual(await self.recv(stay), ["EVENT", "k", ev])

    # --- limites ---
    async def test_too_many_subscriptions_are_closed(self):
        ws = await self.client()
        for i in range(MAX_SUBS):
            await self.subscribe(ws, f"s{i}", {"kinds": [1]})
        await ws.send(json.dumps(["REQ", "extra", {"kinds": [1]}]))
        self.assertEqual((await self.recv(ws))[0:2], ["CLOSED", "extra"])

    async def test_oversized_message_closes_connection(self):
        ws = await self.client()
        await ws.send("x" * 70000)
        with self.assertRaises(ConnectionClosed) as ctx:
            await asyncio.wait_for(ws.recv(), 2)
        self.assertEqual(ctx.exception.rcvd.code, 1009)

    # --- orden de entrega ---
    async def test_delivery_preserves_publication_order(self):
        pub, sub = await self.client(), await self.client()
        await self.subscribe(sub, "s", {"kinds": [24133]})
        events = [make_event(content=f"m{i}") for i in range(20)]
        for ev in events:
            await pub.send(json.dumps(["EVENT", ev]))
        got = []
        while len(got) < 20:
            msg = await self.recv(sub)
            got.append(msg[2]["id"])
        self.assertEqual(got, [e["id"] for e in events])

    # --- carrera: lo publicado DESPUES del EOSE se entrega ---
    async def test_events_after_eose_are_never_lost(self):
        pub, sub = await self.client(), await self.client()
        for round_ in range(10):
            await self.subscribe(sub, f"r{round_}", {"kinds": [24133], "#e": [f"{round_:064x}"]})
            ev = make_event(extra_tags=[["e", f"{round_:064x}"]])
            await pub.send(json.dumps(["EVENT", ev]))
            msg = await self.recv(sub)
            self.assertEqual(msg, ["EVENT", f"r{round_}", ev])

    # --- peticion HTTP normal (no WebSocket) ---
    async def test_plain_http_request_gets_404(self):
        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        writer.write(b"GET / HTTP/1.1\r\nHost: x\r\nAccept: application/nostr+json\r\nConnection: close\r\n\r\n")
        await writer.drain()
        status = (await reader.readline()).decode()
        writer.close()
        self.assertIn("404", status)


if __name__ == "__main__":
    unittest.main()
