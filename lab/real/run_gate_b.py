"""Controlador de la Compuerta B (observacion de Stacker News) de la Fase 1.0A.2. Codigo de laboratorio, solo biblioteca estandar.

Se ejecuta desde PowerShell del propietario con la terminal interactiva (stdin y stdout reales):
  * muestra la URI bunker:// SOLO en esa terminal (pasa por la memoria del controlador, nunca por archivos ni registros);
  * reenvia al firmante las respuestas del propietario (la unica pregunta es la de `connect`; las firmas no se preguntan: se deniegan);
  * impone la ventana (maximo 300 s), reserva tiempo de limpieza, admite Ctrl+C y garantiza la limpieza de Docker ante cualquier error.

Modos:
  check      check-b + preflight-b (sin trafico externo).
  rehearsal  Ensayo LOCAL (relay de laboratorio, cliente NDK local, proyecto Docker propio): `--interactive` lo opera una persona
             en PowerShell; `--auto` lo ejecuta de forma desatendida (stdin simulado: NO sustituye a la comprobacion interactiva).
  run        Compuerta B REAL (relay.primal.net:443). SOLO con autorizacion expresa y ventana indicada por el propietario.

Uso (desde la raiz del repositorio):
  python -X utf8 lab/real/run_gate_b.py check --tls-groups X25519
  python -X utf8 lab/real/run_gate_b.py rehearsal --interactive --scenario full
  python -X utf8 lab/real/run_gate_b.py run --tls-groups X25519 --start 2026-11-20T20:14:00-03:00 --evidence-dir lab/results/gate-b-run
"""
import argparse
import contextlib
import dataclasses
import datetime as dt
import io
import json
import os
import queue
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_gate_a as ga  # noqa: E402

ROOT, UTC = ga.ROOT, ga.UTC
WINDOW_MAX_S, LATEST_START_S, MIN_SESSION_S = 300, 60, 90
POLL_S, PROXY_POLL_S = 0.5, 4.0
MAX_FORWARDED_LINES, MAX_LINE_BYTES = 5, 64
URI_RX = re.compile(rb"bunker://[^\s\x1b]+(?=[\s\x1b])")
LAB_PROJECT = "nip46-gateb-lab"
LAB_COMPOSE = ["docker", "compose", "-f", "lab/real/compose.real.yaml", "-f", "lab/real/compose.gate-b.yaml", "-f", "lab/real/compose.rehearsal.yaml", "-p", LAB_PROJECT]
EXPECTED_END = {"full": "cliente_termino", "manual-stop": "interrupcion_manual", "timeout": "tiempo"}
SCENARIOS = tuple(EXPECTED_END)


def iso(t: dt.datetime) -> str:
    return t.isoformat(timespec="milliseconds")


def min_session_s(window_s: float) -> float:
    """Observacion minima para empezar: 90 s en la ventana real (300 s); proporcional (50 %) en los ensayos cortos."""
    return 90.0 if window_s >= 200 else window_s * 0.5


def cleanup_reserve_s(window_s: float) -> float:
    """Tiempo reservado al final de la ventana para detener procesos y limpiar Docker."""
    return min(40.0, max(15.0, window_s * 0.15))


@dataclasses.dataclass
class Plan:
    kind: str                         # "real" | "lab"
    compose: list
    project: str
    env: dict
    evidence_dir: Path
    start: dt.datetime
    window_s: int
    allow_target: str
    infra: tuple = ("proxy",)
    client: bool = False              # lab: lanzar el cliente NDK local con la URI (por stdin)
    scenario: str = ""
    require_tty: bool = True
    tls_groups: str = "X25519"


def residuals_for(project: str, env: dict) -> dict:
    flt = ["--filter", f"label=com.docker.compose.project={project}"]

    def count(cmd):
        return len(ga.sh(cmd + flt, env, 30).stdout.split())

    return {"contenedores": count(["docker", "ps", "-a", "-q"]), "redes": count(["docker", "network", "ls", "-q"]), "volumenes": count(["docker", "volume", "ls", "-q"])}


def default_prechecks(plan: Plan):
    """check-b y preflight-b (locales, sin trafico externo) con entorno hostil. Devuelve (ok, informe)."""
    pre = plan.evidence_dir / "pre"
    pre.mkdir(parents=True, exist_ok=True)
    env = ga.hostile_env(ga.make_env(ga.GATE_B_RELAY, plan.tls_groups, pre))
    chk = ga.static_check(env, ga.COMPOSE_B)
    senv = json.loads(ga.sh(ga.COMPOSE_B + ["config", "--format", "json"], env).stdout)["services"]["signer"]["environment"]
    effective = {"MODE": senv["MODE"], "APPROVAL_MODE": senv["APPROVAL_MODE"], "RELAY_ATTEMPTS": senv.get("RELAY_ATTEMPTS"),
                 "N_URIS": senv.get("N_URIS"), "SESSION_TTL_S": senv.get("SESSION_TTL_S")}
    check_ok = (all(v for k, v in chk.items() if k != "tls_groups") and effective["MODE"] == "observe" and effective["APPROVAL_MODE"] == "tty"
                and effective["RELAY_ATTEMPTS"] == "1" and effective["N_URIS"] == "1")
    with contextlib.redirect_stdout(io.StringIO()):
        rc = ga.preflight_b(pre, plan.tls_groups)
    return check_ok and rc == 0, {"check_b": check_ok, "efectivo_con_entorno_hostil": effective, "preflight_b_rc": rc}


def spawn_real(cmd, env):
    return subprocess.Popen(cmd, cwd=ROOT, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def default_run_client(plan: Plan, uri: bytes) -> dict:
    """Cliente NDK 2.12.2 local: la URI viaja por su ENTRADA ESTANDAR (nunca por archivo, argumento ni variable). Solo se devuelve un resumen."""
    env = {**plan.env, "SCENARIO": "e8", "BUNKER_FROM_STDIN": "1", "TIMEOUT_MS": "120000", "SIGN_TIMEOUT_MS": "6000"}
    p = ga.sh(plan.compose + ["run", "--rm", "-T", "client"], env, 200, stdin=uri.decode("ascii") + "\n")
    rows = []
    for line in p.stdout.splitlines():
        with contextlib.suppress(json.JSONDecodeError):
            if line.startswith("{"):
                rows.append(json.loads(line))
    ready = next((r for r in rows if r.get("ev") == "ready_result"), {})
    variants = [r for r in rows if r.get("ev") == "variant"]
    return {"returncode": p.returncode, "ready_ok": ready.get("ok"), "user_pub8": ready.get("user_pub8"), "solicitudes_de_firma": len(variants),
            "firmadas": sum(1 for v in variants if v.get("signed")),
            "errores": [str(r["error"])[:80] for r in rows if r.get("error") and "bunker://" not in str(r["error"])][:3]}   # diagnostico sin la URI


@dataclasses.dataclass
class Deps:
    now: Callable = None
    sleep: Callable = None
    sh: Callable = None
    spawn: Callable = None
    residuals: Callable = None
    prechecks: Callable = None
    run_client: Callable = None
    is_tty: Callable = None
    stdin: object = None
    out: object = None
    late: object = None            # lineas escritas por el operador DESPUES de la observacion (p. ej. la confirmacion final)

    def __post_init__(self):
        self.now = self.now or (lambda: dt.datetime.now(UTC))
        self.sleep = self.sleep or time.sleep
        self.sh = self.sh or ga.sh
        self.spawn = self.spawn or spawn_real
        self.residuals = self.residuals or (lambda plan: residuals_for(plan.project, plan.env))
        self.prechecks = self.prechecks or default_prechecks
        self.run_client = self.run_client or default_run_client
        self.is_tty = self.is_tty or (lambda: (sys.stdin.isatty(), sys.stdout.isatty()))
        self.stdin = self.stdin or sys.stdin.buffer
        self.out = self.out or sys.stdout.buffer
        self.late = self.late or queue.Queue()


class Say:
    """Salida de estado del controlador por el mismo canal que la terminal (nunca contiene la URI ni secretos)."""

    def __init__(self, out):
        self.out, self.lock = out, threading.Lock()

    def __call__(self, text: str) -> None:
        with self.lock:
            self.out.write(f"[gate-b] {text}\n".encode("utf-8", "replace"))
            self.out.flush()


class IoRelay:
    """Reenvia la salida del firmante a la terminal del propietario y sus respuestas al firmante. La URI solo pasa por memoria."""

    def __init__(self, proc, D: Deps, on_uri: Callable):
        self.proc, self.D, self.on_uri = proc, D, on_uri
        self.uri_count, self.forwarded, self.dropped, self.buf, self.stopped = 0, 0, 0, b"", False
        self.threads = [threading.Thread(target=self._pump_out, daemon=True), threading.Thread(target=self._pump_in, daemon=True)]

    def start(self):
        for t in self.threads:
            t.start()

    def join_output(self, timeout=2.0):
        self.threads[0].join(timeout)

    def _pump_out(self):
        reader = getattr(self.proc.stdout, "read1", None) or self.proc.stdout.read
        try:
            while chunk := reader(4096):
                self.D.out.write(chunk)
                self.D.out.flush()
                self.buf = (self.buf + chunk)[-8192:]
                while m := URI_RX.search(self.buf):
                    self.uri_count += 1
                    uri, self.buf = m.group(0), self.buf[m.end():]
                    if self.uri_count == 1:
                        self.on_uri(uri)
        except (OSError, ValueError):
            pass

    def _pump_in(self):
        try:
            while line := self.D.stdin.readline():
                if self.stopped:                      # tras la observacion nada se reenvia al firmante: queda para el controlador
                    self.D.late.put(line)
                    continue
                if self.forwarded >= MAX_FORWARDED_LINES or len(line) > MAX_LINE_BYTES:
                    self.dropped += 1
                    continue
                self.proc.stdin.write(line)
                self.proc.stdin.flush()
                self.forwarded += 1
        except (OSError, ValueError):
            pass


class Monitor:
    """Condiciones de parada observables: firma, aprobacion de firma, modo distinto de observe, destino ajeno, reintento."""

    def __init__(self, plan: Plan, D: Deps):
        self.plan, self.D = plan, D
        self.path, self.offset, self.last_proxy = plan.evidence_dir / "evidence.jsonl", 0, 0.0
        self.targets, self.allowed, self.failed, self.warnings = set(), 0, 0, 0

    def _evidence(self):
        if not self.path.exists():
            return None
        with open(self.path, "rb") as fh:
            fh.seek(self.offset)
            data = fh.read()
        end = data.rfind(b"\n") + 1
        self.offset += end
        for line in data[:end].decode("utf-8", "replace").splitlines():
            with contextlib.suppress(json.JSONDecodeError):
                row = json.loads(line)
                if row.get("ev") == "sign_ok":
                    return "firma_detectada"
                if row.get("ev") == "decision" and row.get("kind") == "sign_event" and row.get("approved"):
                    return "aprobacion_de_firma_detectada"
                if row.get("ev") == "session_start" and (row.get("mode") != "observe" or row.get("approval_mode") != "tty"):
                    return "modo_distinto_de_observe"
        return None

    def poll_proxy(self):
        try:
            out = self.D.sh(self.plan.compose + ["logs", "--no-color", "--no-log-prefix", "proxy"], self.plan.env, 15).stdout
        except (OSError, subprocess.SubprocessError):
            self.warnings += 1
            return None
        self.targets, self.allowed, self.failed = set(), 0, 0
        for line in out.splitlines():
            with contextlib.suppress(json.JSONDecodeError):
                row = json.loads(line) if line.startswith("{") else {}
                if row.get("target"):
                    self.targets.add(row["target"])
                self.allowed += row.get("ev") == "connect_allowed"
                self.failed += row.get("ev") == "connect_failed"
        if not self.targets <= {self.plan.allow_target}:
            return "destino_no_autorizado"
        return "reintento_detectado" if self.allowed + self.failed > 1 else None

    def check(self):
        reason = self._evidence()
        t = self.D.now().timestamp()
        if reason is None and t - self.last_proxy >= PROXY_POLL_S:
            self.last_proxy = t
            reason = self.poll_proxy()
        return reason


def summarize(evidence_dir: Path) -> dict:
    path = evidence_dir / "evidence.jsonl"
    rows = []
    if path.exists():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            with contextlib.suppress(json.JSONDecodeError):
                rows.append(json.loads(line))
    by = lambda name: [r for r in rows if r.get("ev") == name]  # noqa: E731
    strip = lambda r: {k: v for k, v in r.items() if k not in ("ts", "ev")}  # noqa: E731
    reqs = by("observed_request")
    start = (by("session_start") or [{}])[0]
    return {"session_start": {k: start.get(k) for k in ("mode", "approval_mode", "relay_host", "max_signatures")},
            "relay_ready": bool(by("relay_ready")), "metodos": {m: sum(1 for r in reqs if r["method"] == m) for m in sorted({r["method"] for r in reqs})},
            "connect_observado": [strip(r) for r in reqs if r["method"] == "connect"],
            "decisiones_connect": [[d.get("approved"), d.get("reason")] for d in by("decision") if d.get("kind") == "connect"],
            "decisiones_sign": [[d.get("approved"), d.get("reason")] for d in by("decision") if d.get("kind") == "sign_event"],
            "observed_sign": [strip(r) for r in by("observed_sign")], "sign_ok": len(by("sign_ok")),
            "respuestas_publicadas": {m: sum(1 for r in by("response_published") if r["method"] == m) for m in sorted({r["method"] for r in by("response_published")})},
            "session_end": (strip(by("session_end")[-1]) if by("session_end") else None), "errores": [[e["where"], e["error_type"]] for e in by("error")]}


def force_cleanup(plan: Plan, D: Deps, meta: dict) -> None:
    flt = ["--filter", f"label=com.docker.compose.project={plan.project}"]
    for kind, rm in (("ps", ["docker", "rm", "-f"]), ("network", ["docker", "network", "rm"]), ("volume", ["docker", "volume", "rm", "-f"])):
        try:
            ls = ["docker", "ps", "-a", "-q"] if kind == "ps" else ["docker", kind, "ls", "-q"]
            ids = D.sh(ls + flt, plan.env, 20).stdout.split()
            if ids:
                D.sh(rm + ids, plan.env, 30)
        except (OSError, subprocess.SubprocessError) as exc:
            meta.setdefault("errores_de_limpieza", []).append(f"{kind}:{type(exc).__name__}")


def execute(plan: Plan, D: Deps) -> dict:
    t_call = D.now()
    deadline = plan.start + dt.timedelta(seconds=plan.window_s)
    latest = plan.start + dt.timedelta(seconds=LATEST_START_S)
    reserve = cleanup_reserve_s(plan.window_s)
    session_end = deadline - dt.timedelta(seconds=reserve)
    say = Say(D.out)
    meta = {"modo": plan.kind, "destino_unico": plan.allow_target, "tls_groups": plan.tls_groups, "ventana_inicio": iso(plan.start),
            "inicio_maximo": iso(latest), "limite_duro": iso(deadline), "reserva_de_limpieza_s": reserve, "fin_de_observacion_previsto": iso(session_end),
            "controlador_invocado": iso(t_call), "conexion_externa_iniciada": False, "lanzamientos_del_firmante": 0, "uri_apariciones_en_terminal": 0,
            "lineas_enviadas_al_firmante": 0, "lineas_descartadas": 0}
    plan.evidence_dir.mkdir(parents=True, exist_ok=True)
    if (plan.evidence_dir / "evidence.jsonl").exists() or (plan.evidence_dir / "run_meta_b.json").exists():
        meta["abortado"] = "el directorio de evidencia ya contiene datos de otra ejecucion (use uno nuevo; no se sobrescribe nada)"
        return meta

    def done(reason=None):
        if reason:
            meta["abortado"] = reason
        meta["fin"] = iso(D.now())
        meta["escaneo_de_secretos"] = {}
        (plan.evidence_dir / "run_meta_b.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        meta["escaneo_de_secretos"] = {**ga.scan(plan.evidence_dir), **{f"pre/{k}": v for k, v in ga.scan(plan.evidence_dir / "pre").items()}} if (plan.evidence_dir / "pre").exists() else ga.scan(plan.evidence_dir)
        (plan.evidence_dir / "run_meta_b.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        return meta

    tty_in, tty_out = D.is_tty()
    meta["tty_stdin"], meta["tty_stdout"] = tty_in, tty_out
    if plan.require_tty and not (tty_in and tty_out):
        return done("stdin/stdout no son una terminal interactiva (NO-GO: la Compuerta B exige la terminal del propietario)")
    if t_call >= deadline:
        return done("ventana vencida")
    if t_call >= latest:
        return done("inicio tardio (mas de 60 s tras el inicio autorizado)")
    try:
        ok, report = D.prechecks(plan)
    except KeyboardInterrupt:
        force_cleanup(plan, D, meta)
        return done("interrupcion manual durante los prechecks (limpieza forzada del proyecto)")
    meta["prechecks"] = report
    meta["prechecks_ok"] = ok
    if not ok:
        return done("check-b/preflight-b fallaron: NO-GO sin conexion externa")
    pre = D.residuals(plan)
    meta["residuos_previos"] = pre
    if sum(pre.values()):
        return done("recursos Docker residuales antes de iniciar")
    now = D.now()
    if now >= latest:
        return done("inicio tardio tras los prechecks")
    need = min_session_s(plan.window_s)
    if (deadline - max(now, plan.start)).total_seconds() < need:
        return done(f"presupuesto insuficiente (< {need:.0f} s de ventana)")
    say(f"Prechecks OK (sin trafico externo). Esperando el inicio {iso(plan.start)}...")
    try:
        while D.now() < plan.start:
            D.sleep(0.2)
    except KeyboardInterrupt:
        return done("interrupcion manual antes del inicio")

    t0 = D.now()
    meta["inicio_real"] = iso(t0)
    reason, proc, relay, mon = None, None, None, Monitor(plan, D)
    client_state = {"done": False, "result": None}
    meta["conexion_externa_iniciada"] = plan.kind == "real"
    try:
        up = D.sh(plan.compose + ["up", "-d", "--wait", *plan.infra], plan.env, max(20.0, min(90.0, (session_end - D.now()).total_seconds())))
        if up.returncode:
            reason = "docker_up_fallo"
        else:
            def on_uri(uri: bytes):
                say("URI mostrada en ESTA terminal (no se guarda). Pegala en el navegador cuando corresponda.")
                if plan.client:
                    def work():
                        try:
                            client_state["result"] = D.run_client(plan, uri)
                        except (OSError, subprocess.SubprocessError) as exc:
                            client_state["result"] = {"error": type(exc).__name__}
                        client_state["done"] = True
                    threading.Thread(target=work, daemon=True).start()

            proc = D.spawn(plan.compose + ["run", "--rm", "-T", "signer"], plan.env)
            meta["lanzamientos_del_firmante"] = 1
            relay = IoRelay(proc, D, on_uri)
            relay.start()
            say(f"Observacion activa hasta {iso(session_end)} (limite duro {iso(deadline)}). Ctrl+C = parada manual.")
            while True:
                if D.now() >= session_end:
                    reason = "tiempo"
                elif proc.poll() is not None:
                    reason = "firmante_termino"
                elif client_state["done"]:
                    D.sleep(1.0)                                    # deja que la evidencia final llegue al archivo
                    reason = "cliente_termino"
                else:
                    reason = mon.check()
                if reason:
                    break
                D.sleep(POLL_S)
    except KeyboardInterrupt:
        reason = "interrupcion_manual"
    except (OSError, subprocess.SubprocessError) as exc:
        reason = f"error_docker:{type(exc).__name__}"
    finally:
        t_stop = D.now()
        meta["motivo_de_fin"] = reason or "error_no_clasificado"
        meta["fin_de_observacion"] = iso(t_stop)
        for step in ("matar", "registros", "down", "forzar", "resumen"):
            try:
                if step == "matar" and proc is not None:
                    if relay:
                        relay.stopped = True
                    with contextlib.suppress(OSError):
                        proc.kill()
                    if relay:
                        relay.join_output()
                        meta["uri_apariciones_en_terminal"] = relay.uri_count
                        meta["lineas_enviadas_al_firmante"], meta["lineas_descartadas"] = relay.forwarded, relay.dropped
                elif step == "registros":
                    logs = D.sh(plan.compose + ["logs", "--no-color", "--no-log-prefix", "proxy"], plan.env, 15).stdout
                    (plan.evidence_dir / "proxy.jsonl").write_text(logs, encoding="utf-8")        # solo host:puerto, bytes y segundos
                    seen = {json.loads(l)["target"] for l in logs.splitlines() if l.startswith("{") and json.loads(l).get("target")}
                    meta["destinos_vistos_por_el_proxy"] = sorted(seen)
                    meta["solo_destino_autorizado"] = seen <= {plan.allow_target}
                    meta["conexiones_tunel"] = sum(1 for l in logs.splitlines() if '"connect_allowed"' in l)
                    meta["conexiones_fallidas"] = sum(1 for l in logs.splitlines() if '"connect_failed"' in l)
                elif step == "down":
                    budget = max(10.0, min(45.0, (deadline - D.now()).total_seconds() - 2))
                    D.sh(plan.compose + ["down", "-v", "--remove-orphans", "-t", "3"], plan.env, budget)
                elif step == "forzar":
                    meta["residuos_tras_down"] = D.residuals(plan)
                    if sum(meta["residuos_tras_down"].values()):
                        force_cleanup(plan, D, meta)
                elif step == "resumen":
                    meta["residuos_finales"] = D.residuals(plan)
                    meta["cliente_local"] = client_state["result"]
                    meta["resumen_de_evidencia"] = summarize(plan.evidence_dir)
            except KeyboardInterrupt:
                meta.setdefault("interrupciones_durante_limpieza", 0)
                meta["interrupciones_durante_limpieza"] += 1
            except (OSError, subprocess.SubprocessError) as exc:
                meta.setdefault("errores_de_limpieza", []).append(f"{step}:{type(exc).__name__}")
                if step == "down":
                    with contextlib.suppress(OSError, subprocess.SubprocessError, KeyboardInterrupt):
                        force_cleanup(plan, D, meta)
        meta["limpieza_s"] = round((D.now() - t_stop).total_seconds(), 2)
        meta["duracion_total_s"] = round((D.now() - t0).total_seconds(), 2)
        meta["dentro_de_la_ventana"] = D.now() <= deadline
        meta.setdefault("residuos_finales", {"contenedores": -1, "redes": -1, "volumenes": -1})
    return done()


def evaluate_lab(meta: dict, plan: Plan, interactive: bool, attestation: bool | None) -> dict:
    """Criterios GO/NO-GO explicitos del ensayo local. None = no aplica en esa variante."""
    s, full = meta.get("resumen_de_evidencia", {}), plan.scenario == "full"
    methods, start = s.get("metodos", {}), s.get("session_start", {})
    sign = s.get("decisiones_sign", [])
    client = meta.get("cliente_local") or {}
    text = json.dumps(s)
    checks = {
        "stdin_stdout_son_terminal_real": (bool(meta.get("tty_stdin") and meta.get("tty_stdout")) if interactive else None),
        "prechecks_check_b_y_preflight_b": bool(meta.get("prechecks_ok")),
        "uri_mostrada_una_sola_vez_en_la_terminal": meta.get("uri_apariciones_en_terminal") == 1,
        "operador_confirma_haber_visto_la_uri": (attestation is True if interactive else None),
        "uri_y_secretos_ausentes_de_archivos": meta.get("escaneo_de_secretos") == {} and "bunker://" not in text,
        "modo_observe_y_tty_efectivos_con_entorno_hostil": start.get("mode") == "observe" and start.get("approval_mode") == "tty",
        "connect_aprobado_manualmente": (s.get("decisiones_connect") == [[True, "humano"]]) if full else s.get("decisiones_connect") == [],
        "solicitudes_nip46_recibidas": (methods.get("connect", 0) >= 1 and methods.get("get_public_key", 0) >= 1 and methods.get("sign_event") == 11) if full else methods == {},
        "sign_event_rechazados_sin_preguntar": (sign == [[False, "modo_observacion"]] * 11 and len(s.get("observed_sign", [])) == 11) if full else sign == [],
        "cliente_ve_todas_las_firmas_denegadas": (client.get("ready_ok") is True and client.get("solicitudes_de_firma") == 11 and client.get("firmadas") == 0) if full else None,
        "cero_firmas": s.get("sign_ok") == 0 and (s.get("session_end") or {}).get("signatures", 0) == 0,
        "cero_aprobaciones_de_firma": all(not a for a, _ in sign),
        "cero_cuentas_ni_destinos_externos": meta.get("solo_destino_autorizado") is True and "stacker.news" not in text,
        "un_solo_lanzamiento_y_un_solo_tunel": meta.get("lanzamientos_del_firmante") == 1 and meta.get("conexiones_tunel", 0) <= 1 and meta.get("conexiones_fallidas", 0) == 0,
        "motivo_de_fin_esperado": meta.get("motivo_de_fin") == EXPECTED_END[plan.scenario],
        "dentro_de_la_ventana": meta.get("dentro_de_la_ventana") is True,
        "limpieza_docker_sin_residuos": sum(meta.get("residuos_finales", {"x": 1}).values()) == 0,
    }
    verdict = "GO" if all(v in (True, None) for v in checks.values()) and not meta.get("abortado") else "NO-GO"
    return {"criterios": checks, "fallidos": [k for k, v in checks.items() if v is False], "veredicto": verdict,
            "nivel": "interactivo real (PowerShell)" if interactive else "desatendido con stdin simulado: NO sustituye la comprobacion interactiva"}


def lab_plan(scenario: str, window_s: int, evidence_dir: Path, require_tty: bool, hostile: bool = True) -> Plan:
    env = {**os.environ, "RELAY_URL": "ws://relay-lab:7777", "PROXY_ALLOW": "relay-lab:7777", "SN_ORIGIN": "https://sn.lab.invalid", "TLS_GROUPS": "",
           "EVIDENCE_DIR": str(evidence_dir.resolve()), "MODE": "observe"}
    if hostile:
        env = ga.hostile_env(env)                 # el override de la Compuerta B debe anular MODE=sign, aprobacion con guion y URI_FILE
    return Plan("lab", LAB_COMPOSE, LAB_PROJECT, env, evidence_dir, dt.datetime.now(UTC) + dt.timedelta(seconds=30), window_s, "relay-lab:7777", infra=("relay-lab", "proxy"),
                client=(scenario == "full"), scenario=scenario, require_tty=require_tty)


def real_plan(start: dt.datetime, tls_groups: str, evidence_dir: Path) -> Plan:
    """Compuerta B real: UNICO destino relay.primal.net:443 (GATE_B_RELAY), compose con el override de observacion, proyecto nip46-real."""
    env = ga.make_env(ga.GATE_B_RELAY, tls_groups, evidence_dir)
    return Plan("real", ga.COMPOSE_B, "nip46-real", env, evidence_dir, start, WINDOW_MAX_S, f"{ga.GATE_B_RELAY}:443", tls_groups=tls_groups)


def install_break_handler() -> None:
    def handler(signum, frame):
        raise KeyboardInterrupt
    for name in ("SIGBREAK", "SIGTERM"):
        if hasattr(signal, name):
            with contextlib.suppress(ValueError, OSError):
                signal.signal(getattr(signal, name), handler)


def rehearsal_auto(scenario: str, window_s: int, evidence_dir: Path) -> dict:
    """Ensayo DESATENDIDO: el controlador corre en un subproceso con stdin simulado. Mide lo mismo que el interactivo salvo la terminal real."""
    cmd = [sys.executable, "-X", "utf8", str(Path(__file__).resolve()), "rehearsal", "--scenario", scenario, "--window-s", str(window_s),
           "--evidence-dir", str(evidence_dir), "--no-tty-required"]
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    p = subprocess.Popen(cmd, cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=flags)
    seen = {"output": b"", "prompt": False, "active": False}
    lock = threading.Lock()

    def reader():
        while chunk := p.stdout.read1(4096):
            with lock:
                seen["output"] += chunk
                seen["prompt"] |= b"Activar esta conexion" in seen["output"]
                seen["active"] |= b"Observacion activa" in seen["output"]

    threading.Thread(target=reader, daemon=True).start()
    t_end = time.time() + window_s + 120
    answered = interrupted = False
    while p.poll() is None and time.time() < t_end:
        with lock:
            prompt, active = seen["prompt"], seen["active"]
        if scenario == "full" and prompt and not answered:
            answered = True
            time.sleep(1.0)
            with contextlib.suppress(OSError):
                p.stdin.write(b"s\n")                       # aprobacion manual de connect
                p.stdin.flush()
                time.sleep(2.0)
                p.stdin.write(b"s\ns\n")                    # respuestas «si» sobrantes: si existiera una pregunta de firma, las consumiria
                p.stdin.flush()
        if scenario == "manual-stop" and active and not interrupted:
            interrupted = True
            time.sleep(4.0)
            p.send_signal(getattr(signal, "CTRL_BREAK_EVENT", signal.SIGINT))
        time.sleep(0.3)
    if p.poll() is None:
        p.kill()
    p.wait(timeout=30)
    time.sleep(0.5)
    out = seen["output"]
    meta_path = evidence_dir / "run_meta_b.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    plan = lab_plan(scenario, window_s, evidence_dir, False)
    result = evaluate_lab(meta, plan, interactive=False, attestation=None)
    result["verificacion_independiente_del_arnes"] = {"apariciones_de_uri_en_la_salida": len(URI_RX.findall(out + b"\n")), "returncode": p.returncode}
    if result["verificacion_independiente_del_arnes"]["apariciones_de_uri_en_la_salida"] != 1:
        result["fallidos"].append("arnes: la URI no aparecio exactamente una vez en la terminal")
        result["veredicto"] = "NO-GO"
    secret = re.search(rb"secret=([A-Za-z0-9_-]+)", out)
    if secret:                                               # el secreto, leido solo aqui, no puede estar en ningun archivo del ensayo
        leaked = [f.name for f in evidence_dir.rglob("*") if f.is_file() and secret.group(1) in f.read_bytes()]
        result["verificacion_independiente_del_arnes"]["archivos_con_el_secreto"] = leaked
        if leaked:
            result["fallidos"].append("arnes: el secreto aparece en archivos")
            result["veredicto"] = "NO-GO"
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["check", "rehearsal", "run"])
    ap.add_argument("--tls-groups", choices=["X25519", "default"], default="X25519")
    ap.add_argument("--evidence-dir", default=None)
    ap.add_argument("--start", help="ISO 8601 con zona horaria (solo run)")
    ap.add_argument("--window-s", type=int, default=None, help="duracion de la ventana en segundos (run: 300 fijo)")
    ap.add_argument("--scenario", choices=SCENARIOS, default="full")
    mx = ap.add_mutually_exclusive_group()
    mx.add_argument("--interactive", action="store_true", help="rehearsal: lo opera una persona en PowerShell (exige terminal real)")
    mx.add_argument("--auto", action="store_true", help="rehearsal: desatendido con stdin simulado")
    ap.add_argument("--no-tty-required", action="store_true", help=argparse.SUPPRESS)
    a = ap.parse_args()
    install_break_handler()
    stamp = dt.datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    default_dir = f"lab/results/gate-b-{'run' if a.mode == 'run' else 'rehearsal'}-{stamp}"
    evidence_dir = Path(a.evidence_dir or default_dir)
    evidence_dir = evidence_dir if evidence_dir.is_absolute() else ROOT / evidence_dir
    if "results" not in evidence_dir.parts:
        print("la evidencia debe ir bajo lab/results/ (excluido de Git)")
        return 2
    if a.mode == "check":
        plan = Plan("real", ga.COMPOSE_B, "nip46-real", {}, evidence_dir, dt.datetime.now(UTC), WINDOW_MAX_S, f"{ga.GATE_B_RELAY}:443", tls_groups=a.tls_groups)
        ok, rep = default_prechecks(plan)
        print(json.dumps(rep, indent=2))
        return 0 if ok else 1
    if a.mode == "rehearsal":
        window = a.window_s or (180 if a.scenario == "full" else 60)
        if not 60 <= window <= WINDOW_MAX_S:
            print("--window-s debe estar entre 60 y 300")
            return 2
        if a.auto:
            res = rehearsal_auto(a.scenario, window, evidence_dir)
            print(json.dumps(res, indent=2, ensure_ascii=False))
            return 0 if res["veredicto"] == "GO" else 1
        plan = lab_plan(a.scenario, window, evidence_dir, require_tty=not a.no_tty_required)
        deps = Deps()
        meta = execute(plan, deps)
        attestation = None
        if a.interactive and meta.get("tty_stdin") and not meta.get("abortado"):
            sys.stdout.write("[gate-b] Viste la URI bunker:// en ESTA terminal? [s/N] ")
            sys.stdout.flush()
            try:
                attestation = deps.late.get(timeout=120).decode("utf-8", "replace").strip().lower() in ("s", "si", "y", "yes")
            except queue.Empty:
                attestation = False
        res = evaluate_lab(meta, plan, interactive=a.interactive, attestation=attestation)
        (evidence_dir / "evaluacion_b.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0 if res["veredicto"] == "GO" else 1
    if not a.start:
        print("run exige --start")
        return 2
    start = dt.datetime.fromisoformat(a.start)
    if start.tzinfo is None:
        print("--start debe llevar zona horaria")
        return 2
    meta = execute(real_plan(start, a.tls_groups, evidence_dir), Deps())
    summary = {k: meta.get(k) for k in ("abortado", "motivo_de_fin", "inicio_real", "fin", "duracion_total_s", "dentro_de_la_ventana", "uri_apariciones_en_terminal",
                                        "conexiones_tunel", "destinos_vistos_por_el_proxy", "residuos_finales", "escaneo_de_secretos")}
    summary["resumen_de_evidencia"] = meta.get("resumen_de_evidencia")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if not meta.get("abortado") else 1


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)        # hilos demonio bloqueados en stdin no deben retener el cierre del interprete
