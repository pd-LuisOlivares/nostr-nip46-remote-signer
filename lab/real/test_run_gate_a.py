"""Pruebas SIN red de la secuencia A1/A2 del lanzador (reloj y ejecutor simulados; solo biblioteca estandar).

Ejecutar desde la raiz del repositorio:  python -X utf8 -m unittest lab/real/test_run_gate_a.py -v
"""
import datetime as dt
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

spec = importlib.util.spec_from_file_location("run_gate_a", Path(__file__).with_name("run_gate_a.py"))
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)

CL = dt.timezone(dt.timedelta(hours=-3))
START = dt.datetime(2026, 11, 21, 17, 0, 0, tzinfo=CL)


class FakeClock:
    def __init__(self, at):
        self.t = at

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += dt.timedelta(seconds=s)

    def advance(self, s):
        self.t += dt.timedelta(seconds=s)


class SequenceCase(unittest.TestCase):
    def run_seq(self, results, clock, per_test_s=20, start=START):
        calls = []

        def one(label, host, tls, base, deadline, clk):
            calls.append((label, host, tls))
            clock.advance(per_test_s)
            return {"etiqueta": label, "destino": f"{host}:443", "intentos": 1, "sonda": {"verdict": results.get(label, "GO")},
                    "abort_global": label in results.get("abort", ())}

        with tempfile.TemporaryDirectory() as tmp:
            meta = g.run_sequence("X25519", Path(tmp), start, clock=clock, sleep=clock.sleep, one=one)
        return meta, calls

    def test_fixed_order_and_one_attempt_per_destination(self):
        meta, calls = self.run_seq({}, FakeClock(START - dt.timedelta(seconds=10)))
        self.assertEqual(calls, [("A1", "relay.primal.net", "X25519"), ("A2", "relay.primal.io", "X25519")])
        self.assertEqual([p["intentos"] for p in meta["pruebas"]], [1, 1])
        self.assertTrue(meta["dentro_de_la_ventana"])
        self.assertEqual(meta["limite_duro_global"], (START + dt.timedelta(seconds=300)).isoformat())

    def test_waits_for_the_start_time_before_any_attempt(self):
        clock = FakeClock(START - dt.timedelta(seconds=30))
        meta, calls = self.run_seq({}, clock)
        self.assertGreaterEqual(dt.datetime.fromisoformat(meta["inicio_real"]), START)
        self.assertEqual(len(calls), 2)

    def test_a2_runs_even_when_a1_is_go_and_also_when_it_is_no_go(self):
        for a1 in ("GO", "NO-GO"):
            with self.subTest(a1=a1):
                meta, calls = self.run_seq({"A1": a1}, FakeClock(START))
                self.assertEqual([c[0] for c in calls], ["A1", "A2"])
                self.assertEqual(meta["comparacion"]["A1"]["verdict"], a1)

    def test_global_abort_in_a1_prevents_a2(self):
        meta, calls = self.run_seq({"abort": ("A1",)}, FakeClock(START))
        self.assertEqual([c[0] for c in calls], ["A1"])
        self.assertEqual(meta["secuencia_interrumpida_tras"], "A1")

    def test_a2_is_skipped_when_less_than_90_seconds_remain(self):
        clock = FakeClock(START)
        meta, calls = self.run_seq({}, clock, per_test_s=215)        # A1 termina a +215 s: quedan 85 s
        self.assertEqual([c[0] for c in calls], ["A1"])
        self.assertIn("omitida", meta["pruebas"][1])
        self.assertEqual(meta["pruebas"][1]["intentos"], 0)

    def test_late_start_aborts_without_any_attempt(self):
        meta, calls = self.run_seq({}, FakeClock(START + dt.timedelta(seconds=61)))
        self.assertEqual((calls, meta.get("abortado")), ([], "inicio fuera de la ventana"))

    def test_start_at_the_edge_is_still_allowed_but_the_total_stays_inside_the_window(self):
        meta, calls = self.run_seq({}, FakeClock(START + dt.timedelta(seconds=59)), per_test_s=60)
        self.assertEqual(len(calls), 2)
        self.assertTrue(meta["dentro_de_la_ventana"])

    def test_worst_case_budget_fits_in_five_minutes(self):
        # A1 inicia como muy tarde a +60 s y tarda como mucho PROBE_CAP_S + limpieza; A2 solo arranca con >= 90 s disponibles.
        worst_a1_end = g.LATEST_START_S + g.PROBE_CAP_S + g.CLEANUP_RESERVE_S
        self.assertLessEqual(worst_a1_end + g.MIN_NEXT_S, g.WINDOW_S + 0)   # 135 + 90 <= 300
        self.assertGreater(g.WINDOW_S - worst_a1_end, g.MIN_NEXT_S)
        self.assertEqual(g.WINDOW_S, 300)

    def test_targets_are_exactly_the_two_authorized_relays_and_never_together(self):
        self.assertEqual(g.SEQUENCE, [("A1", "relay.primal.net"), ("A2", "relay.primal.io")])
        self.assertEqual(g.TARGETS, {"relay.primal.net": 443, "relay.primal.io": 443})
        for label, host in g.SEQUENCE:
            env = g.make_env(host, "X25519", Path(tempfile.mkdtemp()))
            self.assertEqual(env["PROXY_ALLOW"], f"{host}:443")             # UN solo destino por prueba
            self.assertNotIn(",", env["PROXY_ALLOW"])
            self.assertEqual((env["MODE"], env["TLS_GROUPS"]), ("observe", "X25519"))
            other = [h for h in g.TARGETS if h != host][0]
            self.assertIn(f"{other}:443", g.denied_probes(host))           # el otro relay se prueba como DENEGADO
            self.assertNotIn(env["PROXY_ALLOW"], g.denied_probes(host))


class RunOneCase(unittest.TestCase):
    """run_one con subprocess/compose simulados: un solo `run` de la sonda, `down` despues, sin otro destino."""

    def run_one(self, proxy_log, scan_hits=None, residual_after=0):
        sh_calls, run_calls = [], []

        def fake_sh(args, env, timeout=120, stdin=None):
            sh_calls.append((args[len(g.COMPOSE):], env.get("PROXY_ALLOW")))
            return mock.Mock(stdout=proxy_log if "logs" in args else "", returncode=0, stderr="")

        def fake_run(args, **kw):
            run_calls.append((args, kw["env"]["PROXY_ALLOW"], kw["timeout"]))
            return mock.Mock(stdout=json.dumps({"verdict": "GO", "eose": True, "ok": True, "echo": True, "tls": {"version": "TLSv1.3"}}),
                             stderr="", returncode=0)

        residual_calls = iter([{"contenedores": 0, "redes": 0, "volumenes": 0}, {"contenedores": residual_after, "redes": 0, "volumenes": 0}])
        ok_check = {"compose_config_valido": True, "tls_groups": "X25519"}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(g, "sh", fake_sh), mock.patch.object(g.subprocess, "run", fake_run), \
                mock.patch.object(g, "static_check", return_value=ok_check), mock.patch.object(g, "residuals", side_effect=lambda env: next(residual_calls)), \
                mock.patch.object(g, "scan", return_value=scan_hits or {}):
            clock = FakeClock(START)
            meta = g.run_one("A2", "relay.primal.io", "X25519", Path(tmp), START + dt.timedelta(seconds=300), clock)
        return meta, sh_calls, run_calls

    def test_single_probe_then_cleanup_and_only_the_authorized_target(self):
        log = json.dumps({"ev": "connect_allowed", "target": "relay.primal.io:443"}) + "\n"
        meta, sh_calls, run_calls = self.run_one(log)
        self.assertEqual(len(run_calls), 1)
        self.assertEqual(run_calls[0][1], "relay.primal.io:443")
        self.assertLessEqual(run_calls[0][2], g.PROBE_CAP_S)
        self.assertEqual([c[0][0] for c in sh_calls], ["logs", "down"])       # logs y limpieza completa, en ese orden
        self.assertIn("-v", sh_calls[1][0]); self.assertIn("--remove-orphans", sh_calls[1][0])
        self.assertEqual((meta["intentos"], meta["solo_destino_autorizado"], meta["abort_global"]), (1, True, False))
        self.assertEqual(meta["sonda"]["clasificacion_automatica"], "GO")

    def test_any_other_destination_in_the_proxy_log_aborts_the_sequence(self):
        log = json.dumps({"ev": "connect_allowed", "target": "relay.primal.net:443"}) + "\n"
        meta, _, _ = self.run_one(log)
        self.assertEqual((meta["solo_destino_autorizado"], meta["abort_global"]), (False, True))

    def test_secret_in_evidence_or_leftover_resources_abort_the_sequence(self):
        self.assertTrue(self.run_one("", scan_hits={"probe_stdout.json:nsec1": 1})[0]["abort_global"])
        self.assertTrue(self.run_one("", residual_after=1)[0]["abort_global"])

    def test_no_attempt_when_the_remaining_time_is_too_short(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(g.subprocess, "run") as run, \
                mock.patch.object(g, "static_check", return_value={"compose_config_valido": True}), \
                mock.patch.object(g, "residuals", return_value={"contenedores": 0, "redes": 0, "volumenes": 0}):
            meta = g.run_one("A2", "relay.primal.io", "X25519", Path(tmp), START + dt.timedelta(seconds=30), FakeClock(START))
        run.assert_not_called()
        self.assertEqual((meta["intentos"], meta["abort_global"]), (0, True))

    def test_probe_classification_never_promotes_partial_to_go(self):
        base = {"eose": True, "ok": None, "echo": False, "auth_challenge_received": False, "tls": {"version": "TLSv1.3"}}
        self.assertTrue(g.probe_summary({**base, "verdict": "NO-GO"})["clasificacion_automatica"].startswith("PARTIAL"))
        self.assertEqual(g.probe_summary({**base, "verdict": "NO-GO", "auth_challenge_received": True})["clasificacion_automatica"], "NO-GO")
        self.assertEqual(g.probe_summary({"verdict": "NO-GO", "error": "TimeoutError"})["clasificacion_automatica"], "NO-GO")


if __name__ == "__main__":
    unittest.main()
