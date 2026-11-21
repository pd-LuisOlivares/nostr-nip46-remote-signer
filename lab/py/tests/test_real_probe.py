"""Sonda del relay (Compuerta A): un intento, un solo evento, parada ante AUTH, limites de tiempo y sin reintentos."""
import asyncio
import json
import os
import ssl
import sys
import tempfile
import time
import unittest
from unittest import mock

os.environ["LAB_QUIET"] = "1"

from websockets.asyncio.client import connect  # noqa: E402
from websockets.asyncio.server import serve  # noqa: E402

from lab_real.probe import run_probe  # noqa: E402
from lab_real.proxy import build  # noqa: E402
from lab_real.tls import client_context, ssl_kwargs  # noqa: E402
from tests.test_real_proxy import _throwaway_pki  # noqa: E402

LOCAL = mock.patch("lab_real.probe.LAB_HOSTS", {"127.0.0.1"})   # solo para usar ws:// contra un relay falso local


class FakeRelay:
    """Relay falso con comportamiento configurable; cuenta conexiones y mensajes recibidos."""

    def __init__(self, behavior="ok"):
        self.behavior, self.connections, self.received = behavior, 0, []

    async def handler(self, ws):
        self.connections += 1
        if self.behavior == "auth_first":
            await ws.send(json.dumps(["AUTH", "desafio-de-prueba"]))
        async for raw in ws:
            msg = json.loads(raw)
            self.received.append(msg[0])
            if msg[0] == "REQ":
                if self.behavior == "closed_auth":
                    await ws.send(json.dumps(["CLOSED", msg[1], "auth-required: se exige NIP-42"]))
                elif self.behavior == "auth_after_req":
                    await ws.send(json.dumps(["AUTH", "desafio-de-prueba"]))
                elif self.behavior != "silent":
                    await ws.send(json.dumps(["EOSE", msg[1]]))
                    if self.behavior == "double_eose":
                        await ws.send(json.dumps(["EOSE", msg[1]]))
            elif msg[0] == "EVENT":
                ev = msg[1]
                if self.behavior == "reject":
                    await ws.send(json.dumps(["OK", ev["id"], False, "blocked: prueba"]))
                else:
                    await ws.send(json.dumps(["OK", ev["id"], True, ""]))
                    await ws.send(json.dumps(["EVENT", "probe", ev]))


class ProbeBehaviourCase(unittest.IsolatedAsyncioTestCase):
    async def probe(self, behavior, timeout_s=2.0):
        relay = FakeRelay(behavior)
        async with serve(relay.handler, "127.0.0.1", 0) as srv:
            port = srv.sockets[0].getsockname()[1]
            with LOCAL:
                out = await run_probe(f"ws://127.0.0.1:{port}", None, timeout_s=timeout_s)
        return relay, out

    async def test_happy_path_is_go_with_exactly_one_event(self):
        relay, out = await self.probe("ok")
        self.assertEqual((out["verdict"], out["eose"], out["ok"], out["echo"], out["auth_challenge_received"]), ("GO", True, True, True, False))
        self.assertEqual(relay.received, ["REQ", "EVENT"])
        self.assertEqual(relay.connections, 1)

    async def test_repeated_eose_never_publishes_a_second_event(self):
        relay, out = await self.probe("double_eose")
        self.assertEqual(relay.received.count("EVENT"), 1)
        self.assertEqual(out["verdict"], "GO")

    async def test_auth_before_anything_stops_without_authenticating_or_publishing(self):
        relay, out = await self.probe("auth_first")
        self.assertTrue(out["auth_challenge_received"])
        self.assertEqual(out["verdict"], "NO-GO")
        self.assertNotIn("EVENT", relay.received)
        self.assertNotIn("AUTH", relay.received)          # no responde al desafio
        self.assertEqual(relay.connections, 1)

    async def test_auth_after_subscription_stops_without_publishing(self):
        relay, out = await self.probe("auth_after_req")
        self.assertTrue(out["auth_challenge_received"])
        self.assertEqual((out["verdict"], out["eose"]), ("NO-GO", False))
        self.assertEqual(relay.received, ["REQ"])

    async def test_closed_auth_required_is_recorded_and_nothing_is_published(self):
        relay, out = await self.probe("closed_auth")
        self.assertEqual(out["verdict"], "NO-GO")
        self.assertTrue(any("auth-required" in n for n in out["notices"]))
        self.assertNotIn("EVENT", relay.received)

    async def test_rejected_event_is_no_go_and_not_retried(self):
        relay, out = await self.probe("reject")
        self.assertEqual((out["verdict"], out["ok"]), ("NO-GO", False))
        self.assertEqual(relay.received.count("EVENT"), 1)
        self.assertEqual(relay.connections, 1)

    async def test_silent_relay_ends_within_the_time_limit_without_retries(self):
        t0 = time.monotonic()
        relay, out = await self.probe("silent", timeout_s=0.5)
        self.assertLess(time.monotonic() - t0, 3.0)
        self.assertEqual((out["verdict"], out["error"], out["eose"]), ("NO-GO", "TimeoutError", False))
        self.assertEqual((relay.connections, relay.received), (1, ["REQ"]))

    async def test_probe_output_has_no_keys_or_content(self):
        _, out = await self.probe("ok")
        text = json.dumps(out)
        self.assertNotIn("lab-probe", text)
        self.assertRegex(out["probe_pub8"], r"^[0-9a-f]{8}$")
        self.assertNotRegex(text, r"[0-9a-f]{64}")


class BlackHoleThroughProxyCase(unittest.IsolatedAsyncioTestCase):
    """Reproduce localmente el NO-GO de la Compuerta A: el TCP se abre, el ClientHello se envia y nadie responde."""

    async def run_case(self, tls_groups):
        stats = {"conns": 0, "bytes": 0}

        async def black_hole(reader, writer):
            stats["conns"] += 1
            try:
                while data := await reader.read(65536):
                    stats["bytes"] += len(data)
            finally:
                writer.close()

        sink = await asyncio.start_server(black_hole, "127.0.0.1", 0)
        port = sink.sockets[0].getsockname()[1]
        proxy = await build("127.0.0.1", 0, f"127.0.0.1:{port}")
        try:
            t0 = time.monotonic()
            out = await run_probe(f"wss://127.0.0.1:{port}", f"http://127.0.0.1:{proxy.sockets[0].getsockname()[1]}",
                                  timeout_s=1.0, tls_groups=tls_groups)
            return out, stats, time.monotonic() - t0
        finally:
            proxy.close()
            sink.close()

    async def test_no_tls_answer_is_a_timeout_no_go_with_a_single_connection(self):
        out, stats, elapsed = await self.run_case(None)
        self.assertEqual((out["verdict"], out["error"], out["eose"], out["auth_challenge_received"]), ("NO-GO", "TimeoutError", False, False))
        self.assertEqual(stats["conns"], 1, "sin reintentos: una sola conexion TCP")
        self.assertLess(elapsed, 4.0)
        self.assertEqual(out["tls_groups"], "por_defecto")

    async def test_restricted_groups_send_a_much_smaller_client_hello(self):
        default, d_stats, _ = await self.run_case(None)
        small, s_stats, _ = await self.run_case("X25519")
        self.assertEqual((d_stats["conns"], s_stats["conns"]), (1, 1))
        self.assertEqual(small["tls_groups"], "X25519")
        self.assertLess(s_stats["bytes"], 700)
        self.assertLess(s_stats["bytes"], d_stats["bytes"])   # el valor por defecto depende de la version de OpenSSL (1530 B medidos con 3.5)


class TlsContextCase(unittest.IsolatedAsyncioTestCase):
    def test_default_changes_nothing_and_restricted_context_still_verifies(self):
        self.assertIsNone(client_context(None))
        self.assertEqual(ssl_kwargs(""), {})
        ctx = client_context("X25519")
        self.assertEqual((ctx.verify_mode, ctx.check_hostname), (ssl.CERT_REQUIRED, True))
        for bad in ("X25519:P-256", "a b", ";", "x" * 40):
            with self.assertRaises(ValueError):
                client_context(bad)

    async def test_restricted_context_completes_a_verified_wss_handshake_through_the_proxy(self):
        async def handler(ws):
            await ws.send("hola-tls")

        with tempfile.TemporaryDirectory() as tmp:
            pki = _throwaway_pki(tmp, "localhost")
            server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            server_ctx.load_cert_chain(pki["srv.pem"], pki["srv.key"])
            async with serve(handler, "127.0.0.1", 0, ssl=server_ctx) as srv:
                port = srv.sockets[0].getsockname()[1]
                proxy = await build("127.0.0.1", 0, f"localhost:{port}")
                try:
                    proxy_url = f"http://127.0.0.1:{proxy.sockets[0].getsockname()[1]}"
                    ctx = client_context("X25519")
                    ctx.load_verify_locations(pki["ca.pem"])
                    async with connect(f"wss://localhost:{port}", proxy=proxy_url, ssl=ctx) as ws:
                        self.assertEqual(await asyncio.wait_for(ws.recv(), 3), "hola-tls")
                        self.assertEqual(ws.transport.get_extra_info("ssl_object").version(), "TLSv1.3")
                    # sin la CA de prueba el contexto restringido tambien DEBE rechazar el certificado
                    with self.assertRaises(ssl.SSLCertVerificationError):
                        async with connect(f"wss://localhost:{port}", proxy=proxy_url, ssl=client_context("X25519")):
                            pass
                finally:
                    proxy.close()


def closed_port() -> int:
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ProbeFailureCase(unittest.IsolatedAsyncioTestCase):
    """Fallos de proxy, TLS y WSS: la sonda SIEMPRE devuelve un resultado estructurado (nunca una excepcion) y no publica nada."""

    def assert_structured_failure(self, out, error, stage):
        self.assertEqual((out["verdict"], out["error"], out["error_stage"]), ("NO-GO", error, stage))
        self.assertEqual((out["eose"], out["ok"], out["echo"]), (False, None, False))
        text = json.dumps(out)                                     # serializable y sin claves ni contenido
        self.assertNotRegex(text, r"[0-9a-f]{64}")
        self.assertNotIn("lab-probe", text)

    async def through_proxy(self, allow, target_port, tls_groups=None, host="127.0.0.1", timeout_s=1.5):
        proxy = await build("127.0.0.1", 0, allow)
        try:
            return await run_probe(f"wss://{host}:{target_port}", f"http://127.0.0.1:{proxy.sockets[0].getsockname()[1]}",
                                   timeout_s=timeout_s, tls_groups=tls_groups)
        finally:
            proxy.close()

    # ---- proxy
    async def test_proxy_502_is_a_structured_no_go_like_the_a2_failure(self):
        port = closed_port()                                       # el proxy permite el destino pero no logra conectar: 502
        out = await self.through_proxy(f"127.0.0.1:{port}", port, tls_groups="X25519")
        self.assert_structured_failure(out, "InvalidProxyStatus", "conexion")
        self.assertIn("502", out["error_detail"])

    async def test_proxy_403_for_a_destination_not_in_the_allowlist(self):
        out = await self.through_proxy("127.0.0.1:9", closed_port())
        self.assert_structured_failure(out, "InvalidProxyStatus", "conexion")
        self.assertIn("403", out["error_detail"])

    async def test_proxy_that_hangs_up_without_answering(self):
        async def hang_up(reader, writer):
            writer.close()

        srv = await asyncio.start_server(hang_up, "127.0.0.1", 0)
        try:
            out = await run_probe("wss://relay.example.test", f"http://127.0.0.1:{srv.sockets[0].getsockname()[1]}", timeout_s=1.5)
        finally:
            srv.close()
        self.assertEqual((out["verdict"], out["error_stage"]), ("NO-GO", "conexion"))
        self.assertIsNotNone(out["error"])

    async def test_proxy_refusing_connections(self):
        out = await run_probe("wss://relay.example.test", f"http://127.0.0.1:{closed_port()}", timeout_s=1.5)
        self.assert_structured_failure(out, "ConnectionRefusedError", "conexion")

    # ---- TLS
    async def test_untrusted_certificate_is_a_structured_failure(self):
        async def handler(ws):
            await ws.send("x")

        with tempfile.TemporaryDirectory() as tmp:
            pki = _throwaway_pki(tmp, "localhost")
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(pki["srv.pem"], pki["srv.key"])
            async with serve(handler, "127.0.0.1", 0, ssl=ctx) as srv:
                port = srv.sockets[0].getsockname()[1]
                out = await self.through_proxy(f"localhost:{port}", port, tls_groups="X25519", host="localhost")
        self.assert_structured_failure(out, "SSLCertVerificationError", "conexion")
        self.assertIn("certificate verify failed", out["error_detail"])

    async def test_server_that_does_not_speak_tls(self):
        async def plain(reader, writer):
            await reader.read(65536)
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n")
            await writer.drain()
            writer.close()

        srv = await asyncio.start_server(plain, "127.0.0.1", 0)
        try:
            port = srv.sockets[0].getsockname()[1]
            out = await self.through_proxy(f"127.0.0.1:{port}", port)
        finally:
            srv.close()
        self.assertEqual((out["verdict"], out["error_stage"]), ("NO-GO", "conexion"))
        self.assertTrue(out["error"].startswith("SSL"), out["error"])

    # ---- WSS / WebSocket
    async def serve_plain_ws(self, handler):
        async with serve(handler, "127.0.0.1", 0) as srv:
            with LOCAL:
                return await run_probe(f"ws://127.0.0.1:{srv.sockets[0].getsockname()[1]}", None, timeout_s=1.5)

    async def test_relay_closing_with_an_error_code(self):
        async def handler(ws):
            await ws.recv()
            await ws.close(1011)

        out = await self.serve_plain_ws(handler)
        self.assert_structured_failure(out, "ConnectionClosedError", "intercambio")

    async def test_relay_closing_cleanly_before_eose(self):
        async def handler(ws):
            await ws.recv()
            await ws.close(1000)

        out = await self.serve_plain_ws(handler)
        self.assert_structured_failure(out, "ConexionCerradaPorElRelay", "intercambio")

    async def test_malformed_relay_messages_are_structured_failures(self):
        for payload, expected in (("no es json", "JSONDecodeError"), ("{}", "KeyError"), ('["EOSE","probe"]|["EVENT","probe",5]', "AttributeError")):
            with self.subTest(payload=payload):
                async def handler(ws, payload=payload):
                    await ws.recv()
                    for part in payload.split("|"):
                        await ws.send(part)
                    await asyncio.sleep(1)

                out = await self.serve_plain_ws(handler)
                self.assertEqual((out["verdict"], out["error"], out["error_stage"]), ("NO-GO", expected, "intercambio"))

    async def test_http_server_that_is_not_a_websocket(self):
        async def http(reader, writer):
            await reader.read(65536)
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n")
            await writer.drain()
            writer.close()

        srv = await asyncio.start_server(http, "127.0.0.1", 0)
        try:
            with LOCAL:
                out = await run_probe(f"ws://127.0.0.1:{srv.sockets[0].getsockname()[1]}", None, timeout_s=1.5)
        finally:
            srv.close()
        self.assert_structured_failure(out, "InvalidStatus", "conexion")

    async def test_unexpected_exception_is_recorded_by_type_only(self):
        with mock.patch("lab_real.probe.connect", side_effect=RuntimeError("detalle interno que no debe filtrarse")):
            with LOCAL:
                out = await run_probe("ws://127.0.0.1:1", None, timeout_s=1.5)
        self.assert_structured_failure(out, "RuntimeError", "conexion")
        self.assertEqual(out["error_detail"], "excepcion_no_prevista")

    async def test_failure_never_publishes_and_success_output_is_unchanged(self):
        relay = FakeRelay("ok")
        async with serve(relay.handler, "127.0.0.1", 0) as srv:
            with LOCAL:
                out = await run_probe(f"ws://127.0.0.1:{srv.sockets[0].getsockname()[1]}", None, timeout_s=2)
        self.assertEqual(out["verdict"], "GO")
        self.assertFalse({"error", "error_stage", "error_detail"} & set(out))     # el camino de exito no cambia
        self.assertEqual(relay.received, ["REQ", "EVENT"])

    # ---- linea de ordenes: JSON y sin traceback
    async def run_cli(self, env_extra, drop=()):
        env = {k: v for k, v in os.environ.items() if k not in ("RELAY_URL", "PROXY_URL", "TLS_GROUPS") and k not in drop}
        proc = await asyncio.create_subprocess_exec(sys.executable, "-m", "lab_real.probe", env={**env, **env_extra},
                                                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await asyncio.wait_for(proc.communicate(), 20)
        return proc.returncode, stdout.decode(), stderr.decode()

    async def test_cli_prints_structured_json_and_no_traceback_on_connection_failure(self):
        rc, out, err = await self.run_cli({"RELAY_URL": "wss://relay.example.test", "PROXY_URL": f"http://127.0.0.1:{closed_port()}", "TLS_GROUPS": "X25519"})
        result = json.loads(out.strip().splitlines()[-1])
        self.assertEqual((rc, result["verdict"], result["error"], result["error_stage"]), (1, "NO-GO", "ConnectionRefusedError", "conexion"))
        self.assertNotIn("Traceback", err + out)

    async def test_cli_invalid_configuration_is_json_and_opens_no_connection(self):
        rc, out, err = await self.run_cli({"RELAY_URL": "ws://relay.example.test"})            # sin wss ni proxy
        self.assertEqual((rc, json.loads(out)["error"]), (2, "ConfiguracionInvalida"))
        rc, out, _ = await self.run_cli({})                                                  # sin RELAY_URL
        self.assertEqual((rc, json.loads(out)["error"], json.loads(out)["error_stage"]), (2, "ConfiguracionInvalida", "configuracion"))
        self.assertNotIn("Traceback", err)


if __name__ == "__main__":
    unittest.main()
