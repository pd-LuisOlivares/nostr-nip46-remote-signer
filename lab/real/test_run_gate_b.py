"""Pruebas SIN red del controlador de la Compuerta B (reloj, procesos y Docker falsos; solo biblioteca estandar).

Ejecutar desde la raiz del repositorio:  python -X utf8 -m unittest lab/real/test_run_gate_b.py -v
"""
import datetime as dt
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

spec = importlib.util.spec_from_file_location("run_gate_b", Path(__file__).with_name("run_gate_b.py"))
b = importlib.util.module_from_spec(spec)
sys.modules["run_gate_b"] = b
spec.loader.exec_module(b)

CL = dt.timezone(dt.timedelta(hours=-3))
T0 = dt.datetime(2026, 11, 20, 20, 14, 0, tzinfo=CL)
SECRET = "SECRETO_DE_PRUEBA_123"
ZERO = {"contenedores": 0, "redes": 0, "volumenes": 0}

FAKE_SIGNER = r'''
import json, os, sys, time
mode = sys.argv[1]
def w(o):
    with open(os.environ["FAKE_EVIDENCE"], "a", encoding="utf-8") as f:
        f.write(json.dumps(o) + "\n")
print("=== FIRMANTE LISTO ===", flush=True)
print("URI 1: bunker://" + "ab" * 32 + "?relay=ws%3A%2F%2Frelay-lab%3A7777&secret=SECRETO_DE_PRUEBA_123", flush=True)
w({"ev": "session_start", "mode": "observe", "approval_mode": "tty"})
if mode == "exit_now":
    sys.exit(0)
sys.stdout.write("Activar esta conexion? [s/N]\n> "); sys.stdout.flush()
line = sys.stdin.readline()
print("respuesta de %d bytes" % len(line), flush=True)
if mode == "sign_ok":
    w({"ev": "sign_ok"})
if mode == "approved_sign":
    w({"ev": "decision", "kind": "sign_event", "approved": True})
if mode == "bad_mode":
    w({"ev": "session_start", "mode": "sign", "approval_mode": "tty"})
while True:
    time.sleep(1)       # proceso que no termina por si solo (bloqueado): solo la muerte forzada lo detiene
'''


class FakeClock:
    """Reloj simulado: `sleep` avanza el tiempo simulado (con una pausa real minima para dar paso a los procesos hijos)."""

    def __init__(self, at):
        self.t, self.on_sleep = at, None
        self.sleeps = 0

    def __call__(self):
        return self.t

    def advance(self, s):
        self.t += dt.timedelta(seconds=s)

    def sleep(self, s):
        self.sleeps += 1
        if self.on_sleep:
            self.on_sleep(self.sleeps)
        threading.Event().wait(0.01)
        self.advance(s)


class FakeDocker:
    def __init__(self, clock):
        self.clock, self.calls, self.up_rc, self.down_effect, self.proxy_log, self.down_cost = clock, [], 0, None, "", 5

    def __call__(self, args, env, timeout=120, stdin=None):
        word = next((w for w in ("up", "logs", "down") if w in args), "otro")
        self.calls.append((word, list(args), self.clock()))
        if word == "up":
            if isinstance(self.up_rc, Exception):
                raise self.up_rc
            return subprocess.CompletedProcess(args, self.up_rc, "", "")
        if word == "logs":
            return subprocess.CompletedProcess(args, 0, self.proxy_log, "")
        if word == "down":
            self.clock.advance(self.down_cost)
            if self.down_effect:
                raise self.down_effect
        return subprocess.CompletedProcess(args, 0, "id1\n" if "-q" in args else "", "")

    def words(self):
        return [c[0] for c in self.calls]


class Harness(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.clock = FakeClock(T0)
        self.docker = FakeDocker(self.clock)
        self.procs, self.client_calls, self.precheck_calls = [], [], []
        self.out = io.BytesIO()
        self.residual_values = []

    def plan(self, window=100, start=None, client=False, scenario="full", tty=False):
        return b.Plan("real", ["docker", "compose"], "nip46-real", {"FAKE_EVIDENCE": str(self.tmp / "evidence.jsonl")}, self.tmp,
                      start or T0, window, "relay.primal.net:443", client=client, scenario=scenario, require_tty=tty)

    def deps(self, mode="hang", stdin=b"s\n", prechecks=None, tty=(True, True)):
        def spawn(cmd, env):
            p = subprocess.Popen([sys.executable, "-u", "-c", FAKE_SIGNER, mode], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 env={**env, "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", "")})
            self.procs.append(p)
            return p

        def residuals(plan):
            return self.residual_values.pop(0) if self.residual_values else dict(ZERO)

        def default_prechecks(plan):
            self.precheck_calls.append(self.clock())
            return True, {"simulado": True}

        def run_client(plan, uri):
            self.client_calls.append(uri)
            return {"ready_ok": True, "solicitudes_de_firma": 11, "firmadas": 0}

        return b.Deps(now=self.clock, sleep=self.clock.sleep, sh=self.docker, spawn=spawn, residuals=residuals, prechecks=prechecks or default_prechecks,
                      run_client=run_client, is_tty=lambda: tty, stdin=io.BytesIO(stdin), out=self.out)

    def run_plan(self, plan=None, **kw):
        meta = b.execute(plan or self.plan(), self.deps(**kw))
        for p in self.procs:                         # ningun proceso hijo debe sobrevivir a la prueba
            p.poll()
            self.assertIsNotNone(p.returncode, "el proceso del firmante falso debe haber sido terminado por el controlador")
            for pipe in (p.stdin, p.stdout):
                pipe.close()
        return meta


class WindowCase(Harness):
    def test_scheduled_start_waits_and_nothing_external_happens_before_it(self):
        plan = self.plan(start=T0 + dt.timedelta(seconds=30))
        meta = self.run_plan(plan)
        up_time = next(c[2] for c in self.docker.calls if c[0] == "up")
        self.assertGreaterEqual(up_time, plan.start)
        self.assertEqual(len(self.precheck_calls), 1)
        self.assertLess(self.precheck_calls[0], plan.start)                # los prechecks locales pueden ir antes del inicio
        self.assertGreaterEqual(dt.datetime.fromisoformat(meta["inicio_real"]), plan.start)

    def test_late_start_aborts_before_any_docker_or_precheck(self):
        self.clock.t = T0 + dt.timedelta(seconds=61)
        meta = self.run_plan()
        self.assertIn("inicio tardio", meta["abortado"])
        self.assertEqual((self.docker.calls, self.precheck_calls, self.procs), ([], [], []))
        self.assertFalse(meta["conexion_externa_iniciada"])

    def test_start_just_inside_the_grace_period_is_allowed(self):
        self.clock.t = T0 + dt.timedelta(seconds=59)
        meta = self.run_plan(self.plan(window=200))
        self.assertNotIn("abortado", meta)

    def test_expired_window_aborts(self):
        self.clock.t = T0 + dt.timedelta(seconds=101)
        meta = self.run_plan()
        self.assertEqual(meta["abortado"], "ventana vencida")
        self.assertEqual(self.docker.calls, [])

    def test_lateness_caused_by_prechecks_aborts_before_connecting(self):
        def slow(plan):
            self.clock.advance(70)
            return True, {}
        meta = self.run_plan(prechecks=slow)
        self.assertIn("tras los prechecks", meta["abortado"])
        self.assertEqual(self.procs, [])
        self.assertNotIn("up", self.docker.words())

    def test_insufficient_budget_after_prechecks_aborts(self):
        def slow(plan):
            self.clock.advance(55)
            return True, {}
        meta = self.run_plan(prechecks=slow)                          # ventana 100 s: quedan 45 s < 50 s (50 %)
        self.assertIn("presupuesto insuficiente", meta["abortado"])
        self.assertNotIn("up", self.docker.words())

    def test_failed_prechecks_are_no_go_without_connecting(self):
        meta = self.run_plan(prechecks=lambda plan: (False, {"check_b": False}))
        self.assertIn("NO-GO sin conexion externa", meta["abortado"])
        self.assertEqual((self.docker.calls, self.procs), ([], []))

    def test_non_interactive_terminal_is_refused_for_the_real_gate(self):
        meta = self.run_plan(self.plan(tty=True), tty=(False, True))
        self.assertIn("terminal interactiva", meta["abortado"])
        self.assertEqual((self.docker.calls, self.procs), ([], []))

    def test_a_used_evidence_directory_is_refused_and_not_overwritten(self):
        (self.tmp / "evidence.jsonl").write_text("previo" + chr(10), encoding="utf-8")
        meta = self.run_plan()
        self.assertIn("otra ejecucion", meta["abortado"])
        self.assertEqual(((self.tmp / "evidence.jsonl").read_text(encoding="utf-8"), self.docker.calls, self.procs), ("previo" + chr(10), [], []))
        self.assertFalse((self.tmp / "run_meta_b.json").exists())

    def test_residual_resources_before_starting_abort(self):
        self.residual_values = [{"contenedores": 1, "redes": 0, "volumenes": 0}]
        meta = self.run_plan()
        self.assertIn("residuales", meta["abortado"])
        self.assertEqual(self.procs, [])


class BudgetAndCleanupCase(Harness):
    def test_observation_ends_at_deadline_minus_reserve_and_cleanup_fits_the_window(self):
        plan = self.plan(window=300)
        meta = self.run_plan(plan)
        end = dt.datetime.fromisoformat(meta["fin_de_observacion"])
        self.assertEqual(meta["motivo_de_fin"], "tiempo")
        self.assertEqual(meta["reserva_de_limpieza_s"], 40.0)
        self.assertGreaterEqual(end, T0 + dt.timedelta(seconds=260))
        self.assertLess(end, T0 + dt.timedelta(seconds=262))
        self.assertAlmostEqual(meta["limpieza_s"], 5.0, delta=0.5)
        self.assertTrue(meta["dentro_de_la_ventana"])
        self.assertLessEqual(meta["duracion_total_s"], 300)

    def test_a_cleanup_that_overruns_the_window_is_reported_honestly(self):
        self.docker.down_cost = 60
        meta = self.run_plan(self.plan(window=100))
        self.assertFalse(meta["dentro_de_la_ventana"])

    def test_the_real_window_never_exceeds_five_minutes(self):
        self.assertEqual(b.WINDOW_MAX_S, 300)
        self.assertEqual((b.min_session_s(300), b.min_session_s(60)), (90.0, 30.0))
        plan = b.real_plan(T0, "X25519", self.tmp)
        self.assertEqual(plan.window_s, 300)
        self.assertEqual(b.cleanup_reserve_s(300) + b.cleanup_reserve_s(60), 55.0)

    def test_blocked_signer_that_ignores_everything_is_killed_at_the_time_limit(self):
        meta = self.run_plan(mode="hang")
        self.assertEqual(meta["motivo_de_fin"], "tiempo")
        self.assertEqual(self.docker.words().count("down"), 1)
        self.assertEqual(meta["residuos_finales"], ZERO)

    def test_cleanup_always_runs_in_order_kill_logs_down(self):
        self.run_plan()
        self.assertEqual(self.docker.words()[0], "up")
        self.assertLess(self.docker.words().index("logs"), self.docker.words().index("down"))

    def test_down_uses_the_project_scoped_flags(self):
        self.run_plan()
        down = next(c[1] for c in self.docker.calls if c[0] == "down")
        for flag in ("-v", "--remove-orphans"):
            self.assertIn(flag, down)
        self.assertNotIn("--rmi", down)


class DockerErrorCase(Harness):
    def test_up_failure_never_launches_the_signer_and_still_cleans(self):
        self.docker.up_rc = 1
        meta = self.run_plan()
        self.assertEqual(meta["motivo_de_fin"], "docker_up_fallo")
        self.assertEqual((self.procs, meta["lanzamientos_del_firmante"]), ([], 0))
        self.assertIn("down", self.docker.words())

    def test_docker_missing_is_reported_and_cleanup_is_attempted(self):
        self.docker.up_rc = FileNotFoundError("docker")
        meta = self.run_plan()
        self.assertEqual(meta["motivo_de_fin"], "error_docker:FileNotFoundError")
        self.assertIn("down", self.docker.words())

    def test_down_timeout_triggers_forced_project_cleanup(self):
        self.docker.down_effect = subprocess.TimeoutExpired("docker", 45)
        self.residual_values = [dict(ZERO), {"contenedores": 2, "redes": 1, "volumenes": 1}, dict(ZERO)]    # previo, tras down, final
        with mock.patch.object(self.docker, "__call__", wraps=self.docker.__call__):
            meta = self.run_plan()
        self.assertIn("down:TimeoutExpired", meta["errores_de_limpieza"])
        self.assertTrue(any("rm" in c[1] for c in self.docker.calls), "debe forzarse la eliminacion de los recursos del proyecto")
        self.assertEqual(meta["residuos_finales"], ZERO)

    def test_residuals_after_down_are_forced_and_leftovers_are_reported(self):
        self.residual_values = [dict(ZERO), {"contenedores": 1, "redes": 0, "volumenes": 0}, {"contenedores": 1, "redes": 0, "volumenes": 0}]
        meta = self.run_plan()
        self.assertEqual(meta["residuos_tras_down"]["contenedores"], 1)
        self.assertEqual(meta["residuos_finales"]["contenedores"], 1)           # no se oculta: la evaluacion lo marcara como NO-GO

    def test_forced_cleanup_only_targets_the_project_label(self):
        self.residual_values = [dict(ZERO), {"contenedores": 1, "redes": 0, "volumenes": 0}, dict(ZERO)]
        self.run_plan()
        forced = [c[1] for c in self.docker.calls if "ps" in c[1] or "network" in c[1] or "volume" in c[1]]
        self.assertTrue(forced)
        for args in forced:
            if "ls" in args or "ps" in args:
                self.assertIn("label=com.docker.compose.project=nip46-real", args)


class InterruptCase(Harness):
    def test_manual_interrupt_during_observation_cleans_and_reports(self):
        def interrupt(n):
            if n == 20:
                raise KeyboardInterrupt
        self.clock.on_sleep = interrupt
        meta = self.run_plan()
        self.assertEqual(meta["motivo_de_fin"], "interrupcion_manual")
        self.assertIn("down", self.docker.words())
        self.assertEqual(meta["residuos_finales"], ZERO)

    def test_interrupt_before_the_start_never_connects(self):
        def interrupt(n):
            raise KeyboardInterrupt
        self.clock.on_sleep = interrupt
        meta = self.run_plan(self.plan(start=T0 + dt.timedelta(seconds=30)))
        self.assertIn("interrupcion manual antes del inicio", meta["abortado"])
        self.assertNotIn("up", self.docker.words())

    def test_interrupt_during_prechecks_forces_cleanup_and_aborts(self):
        def boom(plan):
            raise KeyboardInterrupt
        meta = self.run_plan(prechecks=boom)
        self.assertIn("interrupcion manual durante los prechecks", meta["abortado"])
        self.assertNotIn("up", self.docker.words())

    def test_a_second_interrupt_during_cleanup_does_not_skip_the_remaining_steps(self):
        raised = []

        def interrupt(n):
            if n == 5:
                raise KeyboardInterrupt
        self.clock.on_sleep = interrupt
        original = self.docker.__call__

        def noisy(args, env, timeout=120, stdin=None):
            if "logs" in args and not raised and self.clock.sleeps >= 5 and not hasattr(self, "_once"):
                self._once = True
                raised.append(1)
                raise KeyboardInterrupt
            return original(args, env, timeout, stdin)
        self.docker = noisy
        self.docker.calls, self.docker.words = [], lambda: []
        meta = self.run_plan()
        self.assertEqual(meta["interrupciones_durante_limpieza"], 1)
        self.assertIn("residuos_finales", meta)


class SafetyCase(Harness):
    def test_a_signature_in_the_evidence_stops_the_session(self):
        meta = self.run_plan(mode="sign_ok")
        self.assertEqual(meta["motivo_de_fin"], "firma_detectada")

    def test_an_approved_sign_decision_stops_the_session(self):
        meta = self.run_plan(mode="approved_sign")
        self.assertEqual(meta["motivo_de_fin"], "aprobacion_de_firma_detectada")

    def test_a_mode_other_than_observe_stops_the_session(self):
        meta = self.run_plan(mode="bad_mode")
        self.assertEqual(meta["motivo_de_fin"], "modo_distinto_de_observe")

    def test_a_destination_other_than_the_authorized_one_stops_the_session(self):
        self.docker.proxy_log = json.dumps({"ev": "connect_allowed", "target": "example.com:443"}) + "\n"
        meta = self.run_plan()
        self.assertEqual(meta["motivo_de_fin"], "destino_no_autorizado")
        self.assertFalse(meta["solo_destino_autorizado"])

    def test_denied_attempts_to_other_destinations_are_also_a_stop_condition(self):
        self.docker.proxy_log = json.dumps({"ev": "connect_denied", "target": "stacker.news:443"}) + "\n"
        self.assertEqual(self.run_plan()["motivo_de_fin"], "destino_no_autorizado")

    def test_a_second_connection_attempt_is_detected_as_a_retry(self):
        line = json.dumps({"ev": "connect_allowed", "target": "relay.primal.net:443"}) + "\n"
        self.docker.proxy_log = line * 2
        self.assertEqual(self.run_plan()["motivo_de_fin"], "reintento_detectado")

    def test_a_failed_then_repeated_connection_counts_as_a_retry(self):
        self.docker.proxy_log = (json.dumps({"ev": "connect_failed", "target": "relay.primal.net:443"}) + "\n") * 2
        self.assertEqual(self.run_plan()["motivo_de_fin"], "reintento_detectado")

    def test_single_authorized_tunnel_is_not_a_violation(self):
        self.docker.proxy_log = json.dumps({"ev": "connect_allowed", "target": "relay.primal.net:443"}) + "\n"
        meta = self.run_plan()
        self.assertEqual((meta["motivo_de_fin"], meta["solo_destino_autorizado"], meta["conexiones_tunel"]), ("tiempo", True, 1))

    def test_the_signer_is_launched_exactly_once_even_if_it_exits(self):
        meta = self.run_plan(mode="exit_now")
        self.assertEqual(meta["motivo_de_fin"], "firmante_termino")
        self.assertEqual((len(self.procs), meta["lanzamientos_del_firmante"]), (1, 1))
        self.assertEqual(self.docker.words().count("up"), 1)

    def test_real_plan_is_restricted_to_primal_net_and_the_observe_override(self):
        plan = b.real_plan(T0, "X25519", self.tmp)
        self.assertEqual(plan.allow_target, "relay.primal.net:443")
        self.assertEqual((plan.env["RELAY_URL"], plan.env["PROXY_ALLOW"], plan.env["TLS_GROUPS"], plan.env["MODE"]),
                         ("wss://relay.primal.net", "relay.primal.net:443", "X25519", "observe"))
        self.assertIn("lab/real/compose.gate-b.yaml", plan.compose)
        self.assertEqual(plan.project, "nip46-real")
        self.assertNotIn("relay.primal.io", json.dumps(plan.env))
        self.assertTrue(plan.require_tty)

    def test_hostile_environment_is_applied_to_the_lab_plan_and_the_override_comes_after_the_base(self):
        plan = b.lab_plan("full", 100, self.tmp, False)
        self.assertEqual((plan.env["MODE"], plan.env["APPROVAL_MODE"], plan.env["URI_FILE"]), ("sign", "scripted", "/ctl/bunker.txt"))
        files = [plan.compose[i + 1] for i, a in enumerate(plan.compose) if a == "-f"]
        self.assertEqual(files, ["lab/real/compose.real.yaml", "lab/real/compose.gate-b.yaml", "lab/real/compose.rehearsal.yaml"])
        self.assertEqual(plan.project, "nip46-gateb-lab")

    @unittest.skipUnless(shutil.which("docker"), "docker no disponible")
    def test_effective_compose_config_stays_observe_under_the_hostile_environment(self):
        plan = b.lab_plan("full", 100, self.tmp, False)
        p = b.ga.sh(plan.compose + ["config", "--format", "json"], plan.env)
        self.assertEqual(p.returncode, 0, p.stderr[-200:])
        env = json.loads(p.stdout)["services"]["signer"]["environment"]
        self.assertEqual((env["MODE"], env["APPROVAL_MODE"], env["APPROVAL_SCRIPT"], env["URI_FILE"], env["RELAY_ATTEMPTS"], env["N_URIS"]),
                         ("observe", "tty", "", "", "1", "1"))


class UriProtectionCase(Harness):
    def test_uri_is_shown_once_on_the_terminal_and_never_written_to_any_file(self):
        meta = self.run_plan()
        self.assertEqual(meta["uri_apariciones_en_terminal"], 1)
        self.assertEqual(self.out.getvalue().count(b"bunker://"), 1)
        self.assertIn(SECRET.encode(), self.out.getvalue())                     # la terminal SI la muestra
        for f in self.tmp.rglob("*"):
            if f.is_file():
                data = f.read_bytes()
                self.assertNotIn(SECRET.encode(), data, f.name)
                self.assertNotIn(b"bunker://", data, f.name)
        self.assertEqual(meta["escaneo_de_secretos"], {})
        self.assertNotIn(SECRET, json.dumps(meta))

    def test_the_status_messages_of_the_controller_never_contain_the_uri(self):
        self.run_plan()
        gate_lines = [l for l in self.out.getvalue().splitlines() if l.startswith(b"[gate-b]")]
        self.assertTrue(gate_lines)
        for l in gate_lines:
            self.assertNotIn(b"bunker://", l)
            self.assertNotIn(SECRET.encode(), l)

    def test_the_local_client_receives_the_uri_only_as_a_call_argument_for_stdin(self):
        meta = self.run_plan(self.plan(client=True))
        self.assertEqual(meta["motivo_de_fin"], "cliente_termino")
        self.assertEqual(len(self.client_calls), 1)
        self.assertTrue(self.client_calls[0].startswith(b"bunker://") and SECRET.encode() in self.client_calls[0])
        self.assertNotIn(SECRET, json.dumps(meta))

    def test_a_secret_that_reaches_a_file_is_detected_by_the_scan(self):
        (self.tmp / "otro_archivo.json").write_text('{"ev":"x","v":"bunker://abc"}' + chr(10), encoding="utf-8")
        meta = self.run_plan()
        self.assertTrue(any("bunker://" in k for k in meta["escaneo_de_secretos"]))

    def test_the_prechecks_directory_is_scanned_too(self):
        (self.tmp / "pre").mkdir()
        (self.tmp / "pre" / "x.json").write_text("nsec1abc", encoding="utf-8")
        self.assertTrue(any(k.startswith("pre/") for k in self.run_plan()["escaneo_de_secretos"]))


class RelayIoCase(unittest.TestCase):
    class FakeProc:
        def __init__(self, stdout=b""):
            self.stdout, self.stdin = io.BytesIO(stdout), io.BytesIO()

    def relay(self, stdin, stdout=b"", stopped=False):
        proc = self.FakeProc(stdout)
        D = b.Deps(stdin=io.BytesIO(stdin), out=io.BytesIO())
        r = b.IoRelay(proc, D, lambda uri: None)
        r.stopped = stopped
        r.start()
        for t in r.threads:
            t.join(2)
        return r, proc, D

    def test_only_a_few_short_lines_reach_the_signer(self):
        lines = [b"s\n"] + [b"x\n"] * 9 + [b"y" * 100 + b"\n"]
        r, proc, _ = self.relay(b"".join(lines))
        self.assertEqual((r.forwarded, r.dropped), (b.MAX_FORWARDED_LINES, len(lines) - b.MAX_FORWARDED_LINES))
        self.assertEqual(proc.stdin.getvalue().count(b"\n"), b.MAX_FORWARDED_LINES)

    def test_after_the_session_input_is_kept_for_the_controller_and_not_forwarded(self):
        r, proc, D = self.relay(b"s\n", stopped=True)
        self.assertEqual((proc.stdin.getvalue(), D.late.get_nowait(), r.forwarded), (b"", b"s\n", 0))

    def test_uri_split_across_chunks_is_still_counted_once_and_passed_in_memory(self):
        captured = []

        class Chunked:
            def __init__(self):
                self.parts = [b"URI 1: bun", b"ker://abc?secret=zzz", b"\nresto\n", b""]

            def read1(self, n):
                return self.parts.pop(0)

        proc = self.FakeProc()
        proc.stdout = Chunked()
        D = b.Deps(stdin=io.BytesIO(b""), out=io.BytesIO())
        r = b.IoRelay(proc, D, captured.append)
        r._pump_out()
        self.assertEqual((r.uri_count, captured), (1, [b"bunker://abc?secret=zzz"]))
        self.assertEqual(D.out.getvalue(), b"URI 1: bunker://abc?secret=zzz\nresto\n")


def good_meta(scenario="full"):
    full = scenario == "full"
    s = {"session_start": {"mode": "observe", "approval_mode": "tty"}, "metodos": {"connect": 1, "get_public_key": 1, "sign_event": 11} if full else {},
         "decisiones_connect": [[True, "humano"]] if full else [], "decisiones_sign": [[False, "modo_observacion"]] * 11 if full else [],
         "observed_sign": [{}] * 11 if full else [], "sign_ok": 0, "session_end": {"reason": "x", "signatures": 0}}
    return {"tty_stdin": True, "tty_stdout": True, "prechecks_ok": True, "uri_apariciones_en_terminal": 1, "escaneo_de_secretos": {}, "resumen_de_evidencia": s,
            "cliente_local": {"ready_ok": True, "solicitudes_de_firma": 11, "firmadas": 0} if full else None, "solo_destino_autorizado": True,
            "lanzamientos_del_firmante": 1, "conexiones_tunel": 1 if full else 0, "conexiones_fallidas": 0,
            "motivo_de_fin": b.EXPECTED_END[scenario], "dentro_de_la_ventana": True, "residuos_finales": dict(ZERO)}


class VerdictCase(unittest.TestCase):
    def plan(self, scenario):
        return b.Plan("lab", [], "p", {}, Path("."), T0, 100, "relay-lab:7777", scenario=scenario)

    def test_good_runs_are_go_for_every_scenario(self):
        for sc in b.SCENARIOS:
            with self.subTest(escenario=sc):
                self.assertEqual(b.evaluate_lab(good_meta(sc), self.plan(sc), True, True)["veredicto"], "GO")
                self.assertEqual(b.evaluate_lab(good_meta(sc), self.plan(sc), False, None)["veredicto"], "GO")

    def test_each_violation_flips_the_verdict_to_no_go_by_its_own_criterion(self):
        mutations = {
            "cero_firmas": lambda m: m["resumen_de_evidencia"].update(sign_ok=1),
            "cero_aprobaciones_de_firma": lambda m: m["resumen_de_evidencia"].update(decisiones_sign=[[True, "humano"]] + [[False, "modo_observacion"]] * 10),
            "uri_mostrada_una_sola_vez_en_la_terminal": lambda m: m.update(uri_apariciones_en_terminal=2),
            "uri_y_secretos_ausentes_de_archivos": lambda m: m.update(escaneo_de_secretos={"evidence.jsonl:bunker://": 1}),
            "limpieza_docker_sin_residuos": lambda m: m.update(residuos_finales={"contenedores": 1, "redes": 0, "volumenes": 0}),
            "dentro_de_la_ventana": lambda m: m.update(dentro_de_la_ventana=False),
            "motivo_de_fin_esperado": lambda m: m.update(motivo_de_fin="tiempo"),
            "cero_cuentas_ni_destinos_externos": lambda m: m.update(solo_destino_autorizado=False),
            "un_solo_lanzamiento_y_un_solo_tunel": lambda m: m.update(conexiones_tunel=2),
            "modo_observe_y_tty_efectivos_con_entorno_hostil": lambda m: m["resumen_de_evidencia"]["session_start"].update(mode="sign"),
            "prechecks_check_b_y_preflight_b": lambda m: m.update(prechecks_ok=False),
            "connect_aprobado_manualmente": lambda m: m["resumen_de_evidencia"].update(decisiones_connect=[]),
            "sign_event_rechazados_sin_preguntar": lambda m: m["resumen_de_evidencia"].update(decisiones_sign=[[False, "modo_observacion"]] * 10),
            "cliente_ve_todas_las_firmas_denegadas": lambda m: m["cliente_local"].update(firmadas=1),
        }
        for criterion, mutate in mutations.items():
            with self.subTest(criterio=criterion):
                m = good_meta()
                mutate(m)
                res = b.evaluate_lab(m, self.plan("full"), True, True)
                self.assertEqual(res["veredicto"], "NO-GO")
                self.assertIn(criterion, res["fallidos"])

    def test_interactive_run_needs_a_real_terminal_and_the_operator_confirmation(self):
        m = good_meta()
        m["tty_stdin"] = False
        self.assertIn("stdin_stdout_son_terminal_real", b.evaluate_lab(m, self.plan("full"), True, True)["fallidos"])
        res = b.evaluate_lab(good_meta(), self.plan("full"), True, False)
        self.assertEqual((res["veredicto"], res["fallidos"]), ("NO-GO", ["operador_confirma_haber_visto_la_uri"]))

    def test_an_aborted_run_is_never_go(self):
        m = good_meta()
        m["abortado"] = "ventana vencida"
        self.assertEqual(b.evaluate_lab(m, self.plan("full"), False, None)["veredicto"], "NO-GO")

    def test_unattended_runs_are_labelled_as_not_replacing_the_interactive_check(self):
        self.assertIn("NO sustituye", b.evaluate_lab(good_meta(), self.plan("full"), False, None)["nivel"])


if __name__ == "__main__":
    unittest.main()
