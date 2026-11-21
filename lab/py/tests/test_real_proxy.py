"""Proxy de salida con lista blanca: solo el destino permitido pasa; todo lo demas se rechaza sin conectar."""
import asyncio
import os
import unittest

os.environ["LAB_QUIET"] = "1"

from websockets.asyncio.client import connect  # noqa: E402

from lab_real.probe import run_probe  # noqa: E402
from unittest import mock  # noqa: E402

from lab_real.proxy import build, parse_allow, parse_connect  # noqa: E402
from lab_relay.server import build as build_relay  # noqa: E402


class ProxyCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.hits = 0

        async def echo(reader, writer):
            self.hits += 1
            while data := await reader.read(1024):
                writer.write(data)
                await writer.drain()
            writer.close()

        self.echo = await asyncio.start_server(echo, "127.0.0.1", 0)
        self.echo_port = self.echo.sockets[0].getsockname()[1]
        self.proxy = await build("127.0.0.1", 0, f"127.0.0.1:{self.echo_port}")
        self.proxy_port = self.proxy.sockets[0].getsockname()[1]

    async def asyncTearDown(self):
        self.proxy.close()
        self.echo.close()

    async def connect_request(self, request: bytes):
        reader, writer = await asyncio.open_connection("127.0.0.1", self.proxy_port)
        writer.write(request)
        await writer.drain()
        return reader, writer

    async def status_of(self, request: bytes) -> str:
        reader, writer = await self.connect_request(request)
        status = (await asyncio.wait_for(reader.readline(), 3)).decode()
        writer.close()
        return status

    async def test_allowed_target_tunnels_bytes(self):
        reader, writer = await self.connect_request(f"CONNECT 127.0.0.1:{self.echo_port} HTTP/1.1\r\nHost: x\r\n\r\n".encode())
        self.assertIn("200", (await reader.readuntil(b"\r\n\r\n")).decode())
        writer.write(b"hola")
        await writer.drain()
        self.assertEqual(await asyncio.wait_for(reader.readexactly(4), 3), b"hola")
        writer.close()

    async def test_other_ports_hosts_and_methods_are_refused_without_connecting(self):
        denied = [
            f"CONNECT 127.0.0.1:{self.echo_port + 1} HTTP/1.1\r\n\r\n",          # puerto distinto
            "CONNECT example.com:443 HTTP/1.1\r\n\r\n",                         # host distinto
            f"CONNECT localhost:{self.echo_port} HTTP/1.1\r\n\r\n",              # alias del mismo equipo: no es el permitido
            f"GET http://127.0.0.1:{self.echo_port}/ HTTP/1.1\r\n\r\n",          # no es CONNECT
            "CONNECT sin-puerto HTTP/1.1\r\n\r\n",
            "BASURA\r\n\r\n",
        ]
        for req in denied:
            with self.subTest(peticion=req.splitlines()[0][:40]):
                self.assertIn("403", await self.status_of(req.encode()))
        self.assertEqual(self.hits, 0, "el destino NO debe recibir ninguna conexion de una peticion rechazada")

    async def test_oversized_or_incomplete_request_is_rejected(self):
        self.assertIn("400", await self.status_of(b"CONNECT " + b"a" * 20000 + b" HTTP/1.1\r\n\r\n"))

    def test_parse_connect(self):
        self.assertEqual(parse_connect("CONNECT Relay.Example:443 HTTP/1.1"), ("relay.example", 443))
        for bad in ("CONNECT x HTTP/1.1", "CONNECT a:b HTTP/1.1", "GET a:1 HTTP/1.1", "CONNECT a:1 FTP", "CONNECT"):
            self.assertIsNone(parse_connect(bad), bad)


class PrimalAllowlistCase(unittest.IsolatedAsyncioTestCase):
    """Compuerta A con relay.primal.net:443: solo ese destino llegaria a conectar; lo demas es 403 sin abrir ninguna conexion."""

    ALLOWED = "relay.primal.net:443"

    async def status(self, proxy_port, request):
        reader, writer = await asyncio.open_connection("127.0.0.1", proxy_port)
        writer.write(request.encode())
        await writer.drain()
        line = (await asyncio.wait_for(reader.readline(), 3)).decode()
        writer.close()
        return line

    async def test_only_the_primal_target_would_connect_and_everything_else_is_403_without_dialing(self):
        opened = []
        real_open = asyncio.open_connection

        async def fake_open(host, port):         # sin red: solo intercepta lo que el PROXY intentaria abrir hacia el exterior
            if host == "127.0.0.1" and port not in (443,):
                return await real_open(host, port)
            opened.append((host, port))
            raise OSError("sin red en la prueba")

        proxy = await build("127.0.0.1", 0, self.ALLOWED)
        port = proxy.sockets[0].getsockname()[1]
        try:
            with mock.patch("lab_real.proxy.asyncio.open_connection", fake_open):
                for target in ("relay.primal.io:443", "relay.primal.net:80", "relay.nsec.app:443", "relay.primal.net.example.test:443",
                               "evil-relay.primal.net:443", "example.com:443", "stacker.news:443", "127.0.0.1:443", "proxy:3128",
                               "relay-lab:7777", "[::1]:443", "10.0.0.1:443"):
                    with self.subTest(destino=target):
                        self.assertIn("403", await self.status(port, f"CONNECT {target} HTTP/1.1\r\n\r\n"))
                self.assertIn("403", await self.status(port, "GET http://relay.primal.net/ HTTP/1.1\r\n\r\n"))
                self.assertEqual(opened, [], "un destino rechazado no debe provocar ninguna conexion saliente")
                # el destino permitido (cualquier capitalizacion) SI intenta conectar, y solo a ese host:puerto
                self.assertIn("502", await self.status(port, "CONNECT Relay.Primal.Net:443 HTTP/1.1\r\n\r\n"))
                self.assertEqual(opened, [("relay.primal.net", 443)])
        finally:
            proxy.close()

    async def test_a2_proxy_allows_only_primal_io_and_refuses_primal_net(self):
        """A2: con PROXY_ALLOW=relay.primal.io:443 el relay de A1 queda denegado (nunca los dos a la vez)."""
        opened = []

        async def fake_open(host, port):
            if host == "127.0.0.1" and port != 443:
                return await real_open(host, port)
            opened.append((host, port))
            raise OSError("sin red en la prueba")

        real_open = asyncio.open_connection
        proxy = await build("127.0.0.1", 0, "relay.primal.io:443")
        port = proxy.sockets[0].getsockname()[1]
        try:
            with mock.patch("lab_real.proxy.asyncio.open_connection", fake_open):
                self.assertIn("403", await self.status(port, "CONNECT relay.primal.net:443 HTTP/1.1\r\n\r\n"))
                self.assertEqual(opened, [])
                self.assertIn("502", await self.status(port, "CONNECT relay.primal.io:443 HTTP/1.1\r\n\r\n"))
                self.assertEqual(opened, [("relay.primal.io", 443)])
        finally:
            proxy.close()

    def test_allow_must_be_exactly_one_host_and_port(self):
        self.assertEqual(parse_allow("Relay.Primal.Net:443"), ("relay.primal.net", 443))
        for bad in ("relay.primal.net:443,relay.primal.io:443", "relay.primal.net:443 relay.primal.io:443", "relay.primal.net",
                    "*.primal.net:443", "wss://relay.primal.net:443", "relay.primal.net:0", "relay.primal.net:99999", ":443", "",
                    "relay.primal.net:443;", "relay primal:443", "-x.net:443"):
            with self.subTest(valor=bad):
                with self.assertRaises(ValueError):
                    parse_allow(bad)
                with self.assertRaises(ValueError):
                    build("127.0.0.1", 0, bad)


class WebsocketThroughProxyCase(unittest.IsolatedAsyncioTestCase):
    """websockets 17.4 usa el proxy por CONNECT y la sonda atraviesa el mismo camino que usara el firmante."""

    async def test_websocket_and_probe_go_through_the_proxy(self):
        async with build_relay("127.0.0.1", 0) as relay:
            rport = relay.sockets[0].getsockname()[1]
            proxy = await build("127.0.0.1", 0, f"127.0.0.1:{rport}")
            try:
                proxy_url = f"http://127.0.0.1:{proxy.sockets[0].getsockname()[1]}"
                async with connect(f"ws://127.0.0.1:{rport}", proxy=proxy_url) as ws:
                    await ws.send('["REQ","s",{"kinds":[1]}]')
                    self.assertEqual(await asyncio.wait_for(ws.recv(), 3), '["EOSE","s"]')
                # La guarda de la sonda: un host que no es del laboratorio exige wss:// y proxy (la sonda completa
                # contra relay-lab se ejercita en el ensayo con Docker).
                with self.assertRaises(ValueError):
                    await run_probe(f"ws://127.0.0.1:{rport}", proxy_url, timeout_s=5)
                with self.assertRaises(ValueError):
                    await run_probe("wss://relay.example.test", None, timeout_s=5)
            finally:
                proxy.close()


def _throwaway_pki(workdir: str, host: str):
    """CA y certificado de servidor DESECHABLES (solo para esta prueba; las claves no salen del directorio temporal)."""
    import datetime
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    def name(cn):
        return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])

    now = datetime.datetime.now(datetime.timezone.utc)
    ca_key, srv_key = ec.generate_private_key(ec.SECP256R1()), ec.generate_private_key(ec.SECP256R1())
    ca = (x509.CertificateBuilder().subject_name(name("ca de prueba")).issuer_name(name("ca de prueba")).public_key(ca_key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(minutes=1))
          .not_valid_after(now + datetime.timedelta(hours=1)).add_extension(x509.BasicConstraints(ca=True, path_length=None), True)
          .sign(ca_key, hashes.SHA256()))
    srv = (x509.CertificateBuilder().subject_name(name(host)).issuer_name(ca.subject).public_key(srv_key.public_key())
           .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(minutes=1))
           .not_valid_after(now + datetime.timedelta(hours=1)).add_extension(x509.SubjectAlternativeName([x509.DNSName(host)]), False)
           .sign(ca_key, hashes.SHA256()))
    paths = {k: os.path.join(workdir, k) for k in ("ca.pem", "srv.pem", "srv.key")}
    with open(paths["ca.pem"], "wb") as fh:
        fh.write(ca.public_bytes(serialization.Encoding.PEM))
    with open(paths["srv.pem"], "wb") as fh:
        fh.write(srv.public_bytes(serialization.Encoding.PEM))
    with open(paths["srv.key"], "wb") as fh:
        fh.write(srv_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    return paths


class WssThroughProxyCase(unittest.IsolatedAsyncioTestCase):
    """TLS de extremo a extremo a traves del proxy: se verifica el certificado del relay (el proxy no lo intercepta)."""

    async def test_wss_through_proxy_verifies_the_certificate(self):
        import ssl
        import tempfile
        from websockets.asyncio.server import serve

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
                    trusting = ssl.create_default_context(cafile=pki["ca.pem"])
                    async with connect(f"wss://localhost:{port}", proxy=proxy_url, ssl=trusting) as ws:
                        self.assertEqual(await asyncio.wait_for(ws.recv(), 3), "hola-tls")
                    # Sin confiar en esa CA (contexto por defecto, como el firmante) la conexion DEBE fallar.
                    with self.assertRaises(ssl.SSLCertVerificationError):
                        async with connect(f"wss://localhost:{port}", proxy=proxy_url):
                            pass
                finally:
                    proxy.close()


if __name__ == "__main__":
    unittest.main()
