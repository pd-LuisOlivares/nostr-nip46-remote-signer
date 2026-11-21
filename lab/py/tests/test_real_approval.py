"""Aprobacion humana (denegacion por defecto) y guardas de configuracion del firmante real."""
import asyncio
import contextlib
import io
import unittest

from lab_real.approval import ApprovalConfigError, ScriptedApprover, decide, make_approver
from lab_real.signer import Config, ConfigError

REAL = {"RELAY_URL": "wss://relay.example.test", "SN_ORIGIN": "https://stacker.news", "PROXY_URL": "http://proxy:3128",
        "EVIDENCE_PATH": ""}
LAB = {"RELAY_URL": "ws://relay-lab:7777", "SN_ORIGIN": "https://sn.lab.invalid", "EVIDENCE_PATH": ""}


class ApprovalTests(unittest.IsolatedAsyncioTestCase):
    async def run_decide(self, script, kind, timeout=1.0):
        with contextlib.redirect_stdout(io.StringIO()):
            return await decide(ScriptedApprover(script), kind, "texto", timeout)

    async def test_yes_is_the_only_way_to_approve(self):
        self.assertEqual((await self.run_decide("sign=y", "sign"))[:2], (True, "humano"))
        for ans in ("n", "x", ""):
            self.assertEqual((await self.run_decide(f"sign={ans}", "sign"))[:2], (False, "humano"))

    async def test_unlisted_kind_and_exhausted_script_are_denied(self):
        self.assertFalse((await self.run_decide("sign=y", "connect"))[0])
        approver = ScriptedApprover("sign=y")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(await approver.ask("sign", "t"))
            self.assertFalse(await approver.ask("sign", "t"))

    async def test_timeout_denies(self):
        ok, reason, _ = await self.run_decide("sign=timeout", "sign", timeout=0.2)
        self.assertEqual((ok, reason), (False, "timeout"))

    async def test_eof_on_terminal_denies(self):
        class Broken:
            async def ask(self, kind, text):
                raise EOFError
        self.assertEqual((await decide(Broken(), "sign", "t", 1))[:2], (False, "error"))


class GuardTests(unittest.TestCase):
    def test_scripted_approval_is_refused_for_real_relays(self):
        with self.assertRaises(ApprovalConfigError):
            make_approver("scripted", "relay.nsec.app", "sign=y")
        make_approver("scripted", "relay-lab", "sign=y")
        with self.assertRaises(ApprovalConfigError):
            make_approver("auto", "relay-lab")

    def test_valid_real_config(self):
        cfg = Config.from_env(REAL)
        self.assertFalse(cfg.lab)
        self.assertEqual((cfg.max_signatures, cfg.window_s, cfg.approval_mode), (2, 120, "tty"))

    def test_default_mode_is_observe_and_signing_needs_an_explicit_mode(self):
        self.assertEqual(Config.from_env(REAL).mode, "observe")      # sin MODE: no se firma nada (Compuerta B por defecto)
        self.assertEqual(Config.from_env({**REAL, "MODE": "sign"}).mode, "sign")

    def test_tls_groups_is_validated_and_optional(self):
        self.assertIsNone(Config.from_env(REAL).tls_groups)
        self.assertEqual(Config.from_env({**REAL, "TLS_GROUPS": "X25519"}).tls_groups, "X25519")
        for bad in ("X25519:secp256r1", "no-existe", "x y", "../x"):
            with self.subTest(grupos=bad):
                with self.assertRaises(ConfigError):
                    Config.from_env({**REAL, "TLS_GROUPS": bad})

    def test_real_config_rules_fail_closed(self):
        cases = {
            "relay sin TLS": {**REAL, "RELAY_URL": "ws://relay.example.test"},
            "sin proxy": {k: v for k, v in REAL.items() if k != "PROXY_URL"},
            "aprobacion automatica": {**REAL, "APPROVAL_MODE": "scripted"},
            "archivo de URI": {**REAL, "URI_FILE": "/ctl/bunker.txt"},
            "origen con barra": {**REAL, "SN_ORIGIN": "https://stacker.news/"},
            "sin origen": {k: v for k, v in REAL.items() if k != "SN_ORIGIN"},
            "tope de firmas excesivo": {**REAL, "MAX_SIGNATURES": "9"},
            "ventana excesiva": {**REAL, "WINDOW_S": "900"},
            "modo desconocido": {**REAL, "MODE": "libre"},
        }
        for name, env in cases.items():
            with self.subTest(caso=name):
                with self.assertRaises(ConfigError):
                    Config.from_env(env)

    def test_lab_config_allows_plain_ws_and_scripted_approval(self):
        cfg = Config.from_env({**LAB, "APPROVAL_MODE": "scripted", "URI_FILE": "/ctl/bunker.txt", "APPROVAL_SCRIPT": "connect=y"})
        self.assertTrue(cfg.lab)


if __name__ == "__main__":
    unittest.main()
