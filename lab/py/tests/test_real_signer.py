"""Denegacion por defecto del firmante real: casos que NDK no ejercita (secretos, estados, repeticion, topes)."""
import asyncio
import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

os.environ["LAB_QUIET"] = "1"

from lab_common import nip44, nostr  # noqa: E402
from lab_real.approval import ScriptedApprover  # noqa: E402
from lab_real.evidence import Evidence  # noqa: E402
from lab_real.signer import Config, Signer  # noqa: E402

T0 = 1_800_000_000
ORIGIN = "https://sn.lab.invalid"


class FakeWS:
    def __init__(self):
        self.sent = []

    async def send(self, raw):
        self.sent.append(json.loads(raw)[1])


class SignerCase(unittest.IsolatedAsyncioTestCase):
    def make(self, script="connect=y,connect=y,sign=y", **cfg_over):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.now = T0
        cfg = Config(relay_url="ws://relay-lab:7777", origin=ORIGIN, approval_mode="scripted", approval_timeout_s=1,
                     uri_file=os.path.join(self.tmp.name, "bunker.txt"), evidence_path=None, **cfg_over).validate()
        self.evpath = os.path.join(self.tmp.name, "evidence.jsonl")
        self.signer = Signer(cfg, Evidence(self.evpath), ScriptedApprover(script), clock=lambda: self.now)
        self.signer.ws = FakeWS()
        self.signer._issue_uris()
        with open(cfg.uri_file, encoding="utf-8") as fh:
            uri = fh.read()
        self.secret = uri.split("secret=")[1]
        self.tpk = self.signer.transport_pk
        self.client_sk = nostr.new_secret()
        self.client_pk = nostr.pubkey_of(self.client_sk)
        self.n = 0

    def request(self, method, params, req_id=None, created_at=None, sk=None, p=None):
        sk = sk or self.client_sk
        self.n += 1
        req_id = req_id or f"r{self.n}"
        key = nip44.get_conversation_key(sk, self.tpk)
        content = nip44.encrypt(json.dumps({"id": req_id, "method": method, "params": params}), key)
        return nostr.sign_event(sk, 24133, [["p", p or self.tpk]], content, created_at or self.now), req_id

    async def call(self, method, params, **kw):
        ev, req_id = self.request(method, params, **kw)
        before = len(self.signer.ws.sent)
        with contextlib.redirect_stdout(io.StringIO()):
            await self.signer.handle_event(ev)
        if len(self.signer.ws.sent) == before:
            return None
        sk = kw.get("sk") or self.client_sk
        body = json.loads(nip44.decrypt(self.signer.ws.sent[-1]["content"], nip44.get_conversation_key(sk, self.tpk)))
        self.assertEqual(body["id"], req_id)
        return body

    async def connect(self, **kw):
        return await self.call("connect", [self.tpk, self.secret], **kw)

    def login_event(self, **over):
        t = {"kind": 27235, "created_at": self.now, "content": "Stacker News Authentication",
             "tags": [["challenge", "ab" * 32], ["u", ORIGIN], ["method", "GET"]], **over}
        return json.dumps(t)

    async def test_connect_with_valid_secret_is_acknowledged_then_secret_is_single_use(self):
        self.make()
        self.assertEqual((await self.connect())["result"], "ack")
        other_sk = nostr.new_secret()
        denied = await self.connect(sk=other_sk)
        self.assertEqual(denied["error"], "unauthorized")

    async def test_wrong_secret_is_refused_and_consumes_no_approval(self):
        self.make("connect=y")
        body = await self.call("connect", [self.tpk, "no-es-el-secreto"])
        self.assertEqual(body["error"], "unauthorized")
        self.assertEqual((await self.connect())["result"], "ack")     # la aprobacion `y` seguia disponible

    async def test_expired_secret_is_refused(self):
        self.make()
        self.now += 601
        self.assertEqual((await self.connect())["error"], "unauthorized")

    async def test_methods_before_connect_are_unauthorized(self):
        self.make()
        for method, params in (("get_public_key", []), ("sign_event", [self.login_event()]), ("ping", [])):
            self.assertEqual((await self.call(method, params))["error"], "unauthorized", method)
        self.assertEqual(self.signer.signatures, 0)

    async def test_denied_connection_stays_denied(self):
        self.make("connect=n,connect=y")
        self.assertEqual((await self.connect())["error"], "unauthorized")
        self.assertEqual((await self.call("get_public_key", []))["error"], "unauthorized")
        self.assertEqual((await self.connect())["error"], "unauthorized")

    async def test_active_client_gets_identity_and_unsupported_methods_are_errors(self):
        self.make()
        await self.connect()
        self.assertEqual((await self.call("get_public_key", []))["result"], self.signer.identity_pk)
        self.assertEqual((await self.call("nip44_encrypt", ["x", "y"]))["error"], "unsupported method")
        self.assertNotEqual(self.signer.identity_pk, self.signer.transport_pk)

    async def test_connection_expires(self):
        self.make(connection_ttl_s=60)
        await self.connect()
        self.now += 61
        self.assertEqual((await self.call("get_public_key", []))["error"], "unauthorized")

    async def test_replayed_event_and_reused_request_id_are_ignored(self):
        self.make()
        ev, _ = self.request("connect", [self.tpk, self.secret], req_id="same")
        with contextlib.redirect_stdout(io.StringIO()):
            await self.signer.handle_event(ev)
            await self.signer.handle_event(ev)                     # mismo evento
        self.assertEqual(len(self.signer.ws.sent), 1)
        self.assertIsNone(await self.call("get_public_key", [], req_id="same"))   # mismo id, otro evento

    async def test_stale_misaddressed_and_forged_events_are_ignored(self):
        self.make()
        self.assertIsNone(await self.connect(created_at=self.now - 121))
        self.assertIsNone(await self.connect(p="f" * 64))
        ev, _ = self.request("connect", [self.tpk, self.secret])
        forged = {**ev, "content": ev["content"][:-4] + "AAAA"}   # id/firma ya no coinciden
        with contextlib.redirect_stdout(io.StringIO()):
            await self.signer.handle_event(forged)
        self.assertEqual(self.signer.ws.sent, [])
        self.assertEqual((await self.connect())["result"], "ack")  # el secreto sigue sin gastar

    async def test_request_cap_ends_the_session(self):
        self.make(max_requests=2)
        await self.connect()
        await self.call("get_public_key", [])
        self.assertFalse(self.signer.finished)
        await self.call("get_public_key", [])
        self.assertTrue(self.signer.finished)

    async def test_signature_cap_and_replayed_challenge(self):
        self.make("connect=y,sign=y,sign=y,sign=y", max_signatures=2)
        await self.connect()
        first = await self.call("sign_event", [self.login_event()])
        signed = json.loads(first["result"])
        self.assertTrue(nostr.verify_event(signed)[0])
        self.assertEqual(signed["pubkey"], self.signer.identity_pk)
        replay = await self.call("sign_event", [self.login_event()])
        self.assertEqual(replay["error"], "unauthorized")
        self.assertEqual(self.signer.signatures, 1)
        second = await self.call("sign_event", [self.login_event(tags=[["challenge", "cd" * 32], ["u", ORIGIN], ["method", "GET"]])])
        self.assertIn("result", second)
        third = await self.call("sign_event", [self.login_event(tags=[["challenge", "ef" * 32], ["u", ORIGIN], ["method", "GET"]])])
        self.assertEqual(third["error"], "unauthorized")
        self.assertEqual(self.signer.signatures, 2)

    async def test_observe_mode_never_signs(self):
        self.make("connect=y,sign=y", mode="observe")
        await self.connect()
        self.assertEqual((await self.call("sign_event", [self.login_event()]))["error"], "unauthorized")
        self.assertEqual(self.signer.signatures, 0)

    def evidence(self, name=None):
        if not os.path.exists(self.evpath):
            return []
        with open(self.evpath, encoding="utf-8") as fh:
            rows = [json.loads(line) for line in fh]
        return [r for r in rows if name is None or r["ev"] == name]

    async def test_observe_mode_has_no_approval_route_whatever_the_approver_says(self):
        """Compuerta B: aunque el aprobador diga que si a todo, no hay firma, ni pregunta, ni evento firmado por la identidad."""
        self.make("connect=y," + "sign=y," * 30, mode="observe")
        self.assertEqual((await self.connect())["result"], "ack")
        identity = (await self.call("get_public_key", []))["result"]
        valid = self.login_event()
        variants = [valid, valid, self.login_event(kind=1), self.login_event(tags=[["challenge", "cd" * 32]]),
                    self.login_event(content="otro"), self.login_event(created_at=self.now - 999), "no es json", "[]",
                    json.dumps({"kind": 27235}), json.dumps({"id": "x", **json.loads(valid)})]
        for raw in variants:
            body = await self.call("sign_event", [raw])
            self.assertEqual(body["error"], "unauthorized")
            self.assertNotIn("sig", body.get("result", ""))
        for params in ([], [1], [valid, "x"], [None], [{"kind": 27235}]):
            self.assertEqual((await self.call("sign_event", params))["error"], "unauthorized")
        self.assertEqual(self.signer.signatures, 0)
        self.assertEqual(self.evidence("sign_ok"), [])
        self.assertEqual({(d["approved"], d["reason"]) for d in self.evidence("decision") if d["kind"] == "sign_event"}, {(False, "modo_observacion")})
        self.assertEqual(len(self.signer.approver.answers["sign"]), 30, "no debe consumirse ninguna respuesta de firma: nunca se pregunta")
        for ev in self.signer.ws.sent:          # todo lo publicado lo firma la clave de TRANSPORTE; la identidad no firma nada
            self.assertEqual(ev["pubkey"], self.signer.transport_pk)
            self.assertNotEqual(ev["pubkey"], identity)

    async def test_observe_mode_records_structure_without_secrets_or_raw_challenges(self):
        self.make("connect=y", mode="observe")
        await self.connect()
        hostile = json.dumps({"kind": 27235, "created_at": self.now - 5, "content": "bunker://x?secret=abc " + "0" * 64,
                              "tags": [["challenge", "ab" * 32], ["u", "https://x.test/" + "f" * 64], ["method", "POST"], ["extra", "1", "2"]],
                              "campo_raro": 1})
        await self.call("sign_event", [self.login_event()])
        await self.call("sign_event", [hostile])
        await self.call("sign_event", ["no es json"])
        obs = self.evidence("observed_sign")
        self.assertEqual(len(obs), 3)
        good, odd, bad = obs
        self.assertEqual((good["kind"], good["n_tags"], good["u_seen"], good["method_seen"], good["challenge_shape"], good["policy_failed"]),
                         (27235, 3, ORIGIN, "GET", "hex64", []))
        self.assertEqual(good["tags"], [["challenge", 1, 64], ["u", 1, len(ORIGIN)], ["method", 1, 3]])
        self.assertEqual((odd["n_tags"], odd["u_seen"], odd["content_seen"], odd["method_seen"]), (4, "<redactado>", "<redactado>", "POST"))
        self.assertIn("campo_raro", odd["fields"])
        self.assertIn("campos", odd["policy_failed"])
        self.assertEqual((bad["json_ok"], bad["policy_failed"]), (False, ["campos", "kind", "pubkey_id", "created_at", "estructura", "challenge", "origen", "metodo", "content", "reutilizacion"]))
        with open(self.evpath, encoding="utf-8") as fh:
            raw_evidence = fh.read()
        for forbidden in ("ab" * 32, "f" * 64, self.secret, "bunker://", "secret="):
            self.assertNotIn(forbidden, raw_evidence)
        self.assertEqual(self.signer.signatures, 0)

    async def test_observe_mode_records_every_method_and_connect_permissions(self):
        self.make("connect=y", mode="observe")
        await self.call("connect", [self.tpk, self.secret, "sign_event:27235,nip44_encrypt"])
        await self.call("get_public_key", [])
        await self.call("switch_relays", [])
        reqs = self.evidence("observed_request")
        self.assertEqual([(r["method"], r["params_n"]) for r in reqs], [("connect", 3), ("get_public_key", 0), ("switch_relays", 0)])
        self.assertEqual(reqs[0]["perms_seen"], "sign_event:27235,nip44_encrypt")
        self.assertEqual(reqs[0]["param_types"], ["str", "str", "str"])
        with open(self.evpath, encoding="utf-8") as fh:
            self.assertNotIn(self.secret, fh.read())

    async def test_sign_mode_emits_no_observation_events(self):
        self.make("connect=y,sign=y")
        await self.connect()
        await self.call("sign_event", [self.login_event()])
        self.assertEqual((self.evidence("observed_request"), self.evidence("observed_sign")), ([], []))
        self.assertEqual(self.signer.signatures, 1)

    async def test_malformed_sign_params_are_rejected(self):
        self.make("connect=y,sign=y")
        await self.connect()
        for params in ([], [1], [self.login_event(), "x"], ["no es json"]):
            self.assertIn((await self.call("sign_event", params))["error"], ("invalid params", "unauthorized"))
        self.assertEqual(self.signer.signatures, 0)

    async def test_terminal_mode_prints_the_uri_and_never_opens_a_file(self):
        self.make()
        cfg = Config(relay_url="ws://relay-lab:7777", origin=ORIGIN, approval_mode="scripted", evidence_path=None).validate()
        sg = Signer(cfg, Evidence(None), ScriptedApprover(""))
        out = io.StringIO()
        with mock.patch("builtins.open", side_effect=AssertionError("no debe abrir archivos")), contextlib.redirect_stdout(out):
            sg._issue_uris()
        self.assertIn("bunker://" + sg.transport_pk, out.getvalue())
        self.assertNotIn(sg.identity_pk, out.getvalue().replace(sg.identity_pk[:8] + "...", ""))   # solo prefijo de la identidad
        for secret_holder in sg.secrets:
            self.assertEqual(len(secret_holder), 64)                    # solo se guarda el SHA-256 del secreto


class RelayAttemptsCase(unittest.IsolatedAsyncioTestCase):
    """Compuerta B: un solo intento de conexion al relay (sin reintentos automaticos del firmante)."""

    async def run_signer(self, attempts, failure):
        cfg = Config(relay_url="ws://relay-lab:7777", origin=ORIGIN, approval_mode="scripted", evidence_path=None, relay_attempts=attempts).validate()
        signer = Signer(cfg, Evidence(None), ScriptedApprover(""))
        calls = []

        async def failing_session():
            calls.append(1)
            raise failure

        sleeps = []

        async def fake_sleep(s):
            sleeps.append(s)

        signer._session = failing_session
        with mock.patch("lab_real.signer.asyncio.sleep", fake_sleep):
            reason = await signer.run()
        return len(calls), reason, sleeps

    async def test_one_attempt_means_one_connection_and_no_wait(self):
        for failure in (OSError("sin ruta"), TimeoutError()):
            with self.subTest(fallo=type(failure).__name__):
                self.assertEqual(await self.run_signer(1, failure), (1, "relay_no_disponible", []))

    async def test_default_keeps_three_attempts_with_pauses_between(self):
        calls, reason, sleeps = await self.run_signer(3, OSError("sin ruta"))
        self.assertEqual((calls, reason, sleeps), (3, "relay_no_disponible", [2, 2]))

    def test_attempts_are_validated_and_read_from_the_environment(self):
        base = {"RELAY_URL": "ws://relay-lab:7777", "SN_ORIGIN": ORIGIN, "EVIDENCE_PATH": ""}
        self.assertEqual(Config.from_env({**base, "RELAY_ATTEMPTS": "1"}).relay_attempts, 1)
        self.assertEqual(Config.from_env(base).relay_attempts, 3)
        for bad in ("0", "4", "x"):
            with self.assertRaises(Exception):
                Config.from_env({**base, "RELAY_ATTEMPTS": bad})


if __name__ == "__main__":
    unittest.main()
