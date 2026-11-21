"""Lanzador de la Compuerta A (sonda del relay) de la Fase 1.0A.2. Codigo de laboratorio, solo biblioteca estandar.

Modos:
  check      Comprueba estaticamente la configuracion (docker compose config). Sin contenedores, sin red.
  check-b    Igual para la Compuerta B (compose.gate-b.yaml, SOLO relay.primal.net) con un entorno hostil (MODE=sign, aprobacion con guion...): debe seguir en observe.
  preflight-b  Proxy de la Compuerta B + comportamiento EFECTIVO del firmante en el contenedor bajo entorno hostil (aprobador que dice si a todo: 0 firmas).
  preflight  Ejercita el proxy REAL con destinos NO permitidos (todos deben dar 403 sin conectar) y comprueba las
             propiedades de aislamiento. NUNCA envia el destino permitido: no genera trafico externo. Limpia al terminar.
  run        UNA sonda en la ventana indicada. Espera al inicio, no empieza si pasa de inicio+60 s, tope duro inicio+120 s,
             sin reintentos, limpieza y escaneo de secretos de la evidencia. Solo con autorizacion explicita del propietario.

El destino esta fijado en TARGETS: otro relay exige editar este archivo (es decir, una decision y autorizacion nuevas).
Uso (desde la raiz del repositorio):
  python -X utf8 lab/real/run_gate_a.py check     --tls-groups X25519
  python -X utf8 lab/real/run_gate_a.py preflight --tls-groups X25519 --evidence-dir lab/results/gate-a-preflight
  python -X utf8 lab/real/run_gate_a.py run --tls-groups X25519 --start 2026-11-21T17:00:00-03:00 --evidence-dir lab/results/gate-a-run
"""
import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ["docker", "compose", "-f", "lab/real/compose.real.yaml", "-p", "nip46-real"]
COMPOSE_B = ["docker", "compose", "-f", "lab/real/compose.real.yaml", "-f", "lab/real/compose.gate-b.yaml", "-p", "nip46-real"]
TARGETS = {"relay.primal.net": 443, "relay.primal.io": 443}   # cada prueba permite UN solo destino en el proxy; nunca los dos a la vez
SEQUENCE = [("A1", "relay.primal.net"), ("A2", "relay.primal.io")]
GATE_B_RELAY = "relay.primal.net"           # la Compuerta B usa EXCLUSIVAMENTE este relay (decision del propietario; relay.primal.io descartado por ahora)
SN_ORIGIN = "https://stacker.news"           # requerido por compose; la sonda no lo usa ni contacta ese sitio
WINDOW_S, LATEST_START_S = 300, 60          # ventana GLOBAL de 5 min (incluye limpieza); no se inicia pasado inicio+60 s
MIN_NEXT_S = 90                              # A2 solo arranca si quedan >= 90 s de ventana
MIN_PROBE_S, PROBE_CAP_S, CLEANUP_RESERVE_S = 45, 60, 15
UTC = dt.timezone.utc
SECRET_SHAPES = [("nsec1", re.compile(r"nsec1", re.I)), ("bunker://", re.compile(r"bunker://", re.I)), ("secret=", re.compile(r"secret=", re.I)),
                 ("authorization", re.compile(r"authorization", re.I)), ("cookie", re.compile(r"cookie", re.I)),
                 ("bearer", re.compile(r"bearer", re.I)), ("64-hex", re.compile(r"[0-9a-fA-F]{64}"))]


def denied_probes(host: str) -> list:
    """Destinos que el proxy configurado para `host` debe rechazar (incluye el OTRO relay de la secuencia)."""
    others = [f"{h}:{p}" for h, p in TARGETS.items() if h != host]
    return others + [f"{host}:80", f"{host}.example.test:443", "relay.nsec.app:443", "example.com:443", "stacker.news:443", "127.0.0.1:443",
                     "proxy:3128", "10.0.0.1:443"]


def sh(args, env, timeout=120, stdin=None):
    return subprocess.run(args, cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, input=stdin)


def make_env(host: str, tls_groups: str, evidence_dir: Path) -> dict:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    return {**os.environ, "RELAY_URL": f"wss://{host}", "PROXY_ALLOW": f"{host}:{TARGETS[host]}", "SN_ORIGIN": SN_ORIGIN,
            "EVIDENCE_DIR": str(evidence_dir.resolve()), "TLS_GROUPS": "" if tls_groups == "default" else tls_groups, "MODE": "observe"}


def static_check(env: dict, compose=COMPOSE) -> dict:
    """Propiedades de la configuracion final segun `docker compose config` (sin crear nada)."""
    p = sh(compose + ["config", "--format", "json"], env)
    if p.returncode:
        return {"compose_config_valido": False, "detalle": p.stderr[-300:]}
    cfg = json.loads(p.stdout)
    proxy, signer = cfg["services"]["proxy"], cfg["services"]["signer"]
    nets = cfg["networks"]
    host, port = env["PROXY_ALLOW"].rsplit(":", 1)
    senv = signer["environment"]
    return {
        "compose_config_valido": True,
        "un_solo_destino_en_el_proxy": proxy["environment"]["PROXY_ALLOW"] == f"{host}:{port}" and "," not in proxy["environment"]["PROXY_ALLOW"] and host in TARGETS,
        "relay_del_firmante_coincide": senv["RELAY_URL"] == f"wss://{host}" and TARGETS[host] == 443,
        "firmante_solo_en_red_interna": list(signer["networks"]) == ["real_internal"] and nets["real_internal"].get("internal") is True,
        "proxy_en_red_interna_y_de_salida": sorted(proxy["networks"]) == ["real_egress", "real_internal"] and not nets["real_egress"].get("internal"),
        "sin_puertos_publicados": not proxy.get("ports") and not signer.get("ports"),
        "firmante_sin_logs_de_docker": (signer.get("logging") or {}).get("driver") == "none",
        "endurecimiento": all(s.get("read_only") is True and s.get("cap_drop") == ["ALL"] and "no-new-privileges:true" in s.get("security_opt", [])
                              for s in (proxy, signer)),
        "modo_observacion_por_defecto": senv["MODE"] == "observe",
        "firmante_sin_aprobacion_automatica": senv["APPROVAL_MODE"] == "tty" and not senv.get("APPROVAL_SCRIPT") and not senv.get("URI_FILE"),
        "tls_groups": senv.get("TLS_GROUPS") or "por_defecto",
        "proxy_del_firmante": senv["PROXY_URL"] == "http://proxy:3128",
    }


def residuals(env: dict) -> dict:
    def count(cmd):
        out = sh(cmd, env).stdout.split()
        return len(out)
    return {"contenedores": count(["docker", "ps", "-a", "--filter", "name=nip46-real", "-q"]),
            "redes": count(["docker", "network", "ls", "--filter", "name=nip46-real", "-q"]),
            "volumenes": count(["docker", "volume", "ls", "--filter", "name=nip46-real", "-q"])}


def scan(directory: Path) -> dict:
    hits = {}
    for f in sorted(directory.glob("*")):
        if f.is_file():
            text = f.read_text(encoding="utf-8", errors="replace")
            for name, rx in SECRET_SHAPES:
                n = len(rx.findall(text))
                if n:
                    hits[f"{f.name}:{name}"] = n
    return hits


def verdict_of(checks: dict) -> str:
    return "PASS" if all(v for k, v in checks.items() if k not in ("tls_groups", "detalle")) else "FAIL"


def preflight(env: dict, evidence_dir: Path, compose=COMPOSE, report_name="preflight.json") -> int:
    report = {"modo": "preflight (sin trafico externo: nunca se envia el destino permitido)", "destino": env["PROXY_ALLOW"], "tls_groups": env["TLS_GROUPS"] or "por_defecto"}
    report["estatico"] = static_check(env, compose)
    report["residuos_previos"] = residuals(env)
    host = env["RELAY_URL"].removeprefix("wss://")
    probes = denied_probes(host)
    assert env["PROXY_ALLOW"] not in probes
    script = ("import socket,sys\nres={}\nfor t in sys.argv[1:]:\n  s=socket.create_connection(('proxy',3128),5)\n"
              "  s.sendall(('CONNECT '+t+' HTTP/1.1\\r\\n\\r\\n').encode())\n  res[t]=s.recv(64).split(b'\\r\\n')[0].decode()\n  s.close()\n"
              "s=socket.create_connection(('proxy',3128),5)\ns.sendall(b'GET http://@HOST@/ HTTP/1.1\\r\\n\\r\\n')\n"
              "res['GET http://@HOST@/']=s.recv(64).split(b'\\r\\n')[0].decode()\nprint(__import__('json').dumps(res))\n").replace("@HOST@", host)
    try:
        up = sh(compose + ["up", "-d", "--wait", "proxy"], env, timeout=180)
        report["proxy_arrancado"] = up.returncode == 0
        if up.returncode == 0:
            run = sh(compose + ["run", "--rm", "-T", "--no-deps", "signer", "python", "-c", script, *probes], env, timeout=120)
            statuses = json.loads(run.stdout.strip().splitlines()[-1]) if run.returncode == 0 and run.stdout.strip() else {}
            report["respuestas_del_proxy"] = statuses
            logs = [json.loads(l) for l in sh(compose + ["logs", "--no-color", "--no-log-prefix", "proxy"], env).stdout.splitlines() if l.startswith("{")]
            evs = [l.get("ev") for l in logs]
            report["registro_del_proxy"] = {"eventos": {e: evs.count(e) for e in sorted(set(evs))}}
            report["todos_rechazados_con_403"] = bool(statuses) and all("403" in v for v in statuses.values()) and len(statuses) == len(probes) + 1
            report["sin_conexion_saliente"] = "connect_allowed" not in evs and "connect_failed" not in evs and "tunnel_closed" not in evs
            # Propiedades de los contenedores en ejecucion (el firmante se crea con `run`, ya terminado: se inspecciona el proxy y la red)
            inspect = json.loads(sh(["docker", "inspect", "nip46-real-proxy-1"], env).stdout)[0]
            hc = inspect["HostConfig"]
            report["proxy_inspeccion"] = {"puertos_publicados": hc.get("PortBindings") or {}, "solo_lectura": hc.get("ReadonlyRootfs"),
                                          "cap_drop": hc.get("CapDrop"), "usuario": inspect["Config"].get("User") or "imagen (lab, uid 10001)"}
            net = json.loads(sh(["docker", "network", "inspect", "nip46-real_real_internal", "nip46-real_real_egress"], env).stdout)
            report["redes"] = {n["Name"]: {"internal": n["Internal"], "contenedores": sorted(c["Name"] for c in n["Containers"].values())} for n in net}
            report["red_interna_correcta"] = report["redes"]["nip46-real_real_internal"]["internal"] is True and not report["redes"]["nip46-real_real_egress"]["internal"]
    finally:
        sh(compose + ["down", "-v", "--remove-orphans"], env, timeout=120)
    report["residuos_finales"] = residuals(env)
    checks = {"estatico": all(v for k, v in report["estatico"].items() if k != "tls_groups"),
              "sin_residuos_previos": sum(report["residuos_previos"].values()) == 0, "proxy_arrancado": report.get("proxy_arrancado", False),
              "todos_rechazados_con_403": report.get("todos_rechazados_con_403", False), "sin_conexion_saliente": report.get("sin_conexion_saliente", False),
              "red_interna_correcta": report.get("red_interna_correcta", False), "sin_puertos": report.get("proxy_inspeccion", {}).get("puertos_publicados") == {},
              "sin_residuos_finales": sum(report["residuos_finales"].values()) == 0}
    report["comprobaciones"], report["veredicto"] = checks, "PASS" if all(checks.values()) else "FAIL"
    (evidence_dir / report_name).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"comprobaciones": checks, "veredicto": report["veredicto"], "destino": env["PROXY_ALLOW"]}, indent=2))
    return 0 if report["veredicto"] == "PASS" else 1


BEHAVIOR_SCRIPT = r"""
import asyncio, contextlib, io, json, os, time
from lab_common import nip44, nostr
from lab_real.approval import ScriptedApprover
from lab_real.evidence import Evidence
from lab_real.signer import Config, Signer


class WS:
    def __init__(self):
        self.sent = []

    async def send(self, raw):
        self.sent.append(json.loads(raw)[1])


async def main():
    cfg = Config.from_env({**os.environ, "EVIDENCE_PATH": ""})                    # configuracion EFECTIVA del contenedor
    signer = Signer(cfg, Evidence(None), ScriptedApprover("connect=y," + "sign=y," * 10))   # aprobador que dice SI a todo
    signer.ws = WS()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        signer._issue_uris()                                                      # la URI NO se imprime: solo se extrae el secreto
    secret = buf.getvalue().split("secret=")[1].split()[0]
    sk = nostr.new_secret()
    key = nip44.get_conversation_key(sk, signer.transport_pk)
    n = [0]

    async def call(method, params):
        n[0] += 1
        content = nip44.encrypt(json.dumps({"id": "r%d" % n[0], "method": method, "params": params}), key)
        ev = nostr.sign_event(sk, 24133, [["p", signer.transport_pk]], content, int(time.time()))
        with contextlib.redirect_stdout(io.StringIO()):
            await signer.handle_event(ev)
        return json.loads(nip44.decrypt(signer.ws.sent[-1]["content"], key))

    connect = await call("connect", [signer.transport_pk, secret])
    results = []
    for i in range(3):
        login = {"kind": 27235, "created_at": int(time.time()), "content": "Stacker News Authentication",
                 "tags": [["challenge", ("%02x" % (i + 1)) * 32], ["u", cfg.origin], ["method", "GET"]]}
        results.append((await call("sign_event", [json.dumps(login)])).get("error"))
    print(json.dumps({"mode": cfg.mode, "approval_mode": cfg.approval_mode, "relay_url": cfg.relay_url, "connect": connect.get("result"),
                      "sign_errors": results, "signatures": signer.signatures, "sign_answers_left": len(signer.approver.answers["sign"]),
                      "sent_pubkeys_are_transport_only": all(e["pubkey"] == signer.transport_pk for e in signer.ws.sent)}))


asyncio.run(main())
"""


def hostile_env(env: dict) -> dict:
    """Lo que dejaria una sesion de PowerShell mal limpiada (Compuerta C anterior, guion de ensayo, archivo de URI)."""
    return {**env, "MODE": "sign", "APPROVAL_MODE": "scripted", "APPROVAL_SCRIPT": "connect=y,sign=y", "URI_FILE": "/ctl/bunker.txt",
            "MAX_SIGNATURES": "3", "N_URIS": "3"}


def preflight_b(evidence_dir: Path, tls_groups: str) -> int:
    """Compuerta B (solo relay.primal.net) bajo entorno hostil, SIN trafico externo: proxy + comportamiento efectivo del firmante."""
    env = hostile_env(make_env(GATE_B_RELAY, tls_groups, evidence_dir))
    rc = preflight(env, evidence_dir, COMPOSE_B, "preflight_b_proxy.json")
    behavior = {}
    try:
        run = sh(COMPOSE_B + ["run", "--rm", "-T", "--no-deps", "signer", "python", "-c", BEHAVIOR_SCRIPT], env, timeout=120)
        behavior = json.loads(run.stdout.strip().splitlines()[-1]) if run.returncode == 0 and run.stdout.strip() else {"error": run.stderr[-300:]}
    finally:
        sh(COMPOSE_B + ["down", "-v", "--remove-orphans"], env, timeout=60)
    leftovers = residuals(env)
    checks = {"proxy_preflight_pass": rc == 0, "modo_efectivo_observe": behavior.get("mode") == "observe",
              "aprobacion_efectiva_tty": behavior.get("approval_mode") == "tty", "relay_efectivo": behavior.get("relay_url") == f"wss://{GATE_B_RELAY}",
              "connect_ack": behavior.get("connect") == "ack", "firmas_denegadas": behavior.get("sign_errors") == ["unauthorized"] * 3,
              "cero_firmas": behavior.get("signatures") == 0, "ninguna_pregunta_de_firma": behavior.get("sign_answers_left") == 10,
              "solo_clave_de_transporte_firma": behavior.get("sent_pubkeys_are_transport_only") is True, "sin_residuos": sum(leftovers.values()) == 0}
    report = {"entorno_hostil": {k: env[k] for k in ("MODE", "APPROVAL_MODE", "APPROVAL_SCRIPT", "URI_FILE")}, "comportamiento": behavior,
              "comprobaciones": checks, "veredicto": "PASS" if all(checks.values()) else "FAIL", "residuos": leftovers}
    (evidence_dir / "preflight_b.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"comprobaciones": checks, "veredicto": report["veredicto"], "relay": GATE_B_RELAY}, indent=2))
    return 0 if report["veredicto"] == "PASS" else 1


def probe_summary(out: dict) -> dict:
    keys = ("verdict", "eose", "eose_ms", "ok", "ok_ms", "echo", "echo_ms", "auth_challenge_received", "notices", "error", "tls_groups")
    s = {k: out.get(k) for k in keys}
    tls = out.get("tls") or {}
    s["tls"] = {k: tls.get(k) for k in ("version", "cipher", "verify_required", "check_hostname", "cert_subject_cn", "cert_not_after")} if tls else None
    if out.get("verdict") == "GO":
        s["clasificacion_automatica"] = "GO"
    elif out.get("auth_challenge_received") or out.get("ok") is False or not tls:
        s["clasificacion_automatica"] = "NO-GO"
    else:
        s["clasificacion_automatica"] = "PARTIAL (WSS con TLS verificado, falta alguno de eose/ok/echo; la clasificacion final la hace el informe)"
    return s


def run_one(label: str, host: str, tls_groups: str, base_dir: Path, deadline: dt.datetime, clock=lambda: dt.datetime.now(UTC)) -> dict:
    """UNA prueba contra UN destino: proxy con ese unico host:puerto, un solo intento, limpieza completa al terminar."""
    d = base_dir / label
    env = make_env(host, tls_groups, d)
    meta = {"etiqueta": label, "destino": env["PROXY_ALLOW"], "tls_groups": env["TLS_GROUPS"] or "por_defecto", "intentos": 0}
    chk = static_check(env)
    pre = residuals(env)
    if not all(v for k, v in chk.items() if k != "tls_groups") or sum(pre.values()):
        meta.update(abortado="la comprobacion estatica o la ausencia de residuos previos fallaron", comprobacion=chk, residuos_previos=pre, abort_global=True)
        return meta
    t0 = clock()
    meta["inicio_real"] = t0.isoformat(timespec="milliseconds")
    remaining = (deadline - t0).total_seconds()
    if remaining < MIN_PROBE_S:
        meta.update(abortado=f"quedan {remaining:.0f} s (< {MIN_PROBE_S} s): no se inicia", abort_global=True)
        return meta
    meta["intentos"] = 1                                               # UN intento por destino: no hay bucle ni reintento en este archivo
    try:
        p = subprocess.run(COMPOSE + ["run", "--rm", "-T", "signer", "python", "-m", "lab_real.probe"], cwd=ROOT, env=env, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=min(PROBE_CAP_S, remaining - CLEANUP_RESERVE_S))
        meta["returncode"] = p.returncode
        (d / "probe_stdout.json").write_text(p.stdout, encoding="utf-8")
        (d / "probe_stderr_tail.txt").write_text(p.stderr[-600:], encoding="utf-8")
        try:
            meta["sonda"] = probe_summary(json.loads(p.stdout.strip().splitlines()[-1]))
        except (json.JSONDecodeError, IndexError):
            meta["sonda"] = None
    except subprocess.TimeoutExpired:
        meta["abortado"] = "limite de tiempo de la prueba alcanzado"
    meta["fin_sonda"] = clock().isoformat(timespec="milliseconds")
    logs = sh(COMPOSE + ["logs", "--no-color", "--no-log-prefix", "proxy"], env).stdout
    (d / "proxy.jsonl").write_text(logs, encoding="utf-8")
    try:
        sh(COMPOSE + ["down", "-v", "--remove-orphans"], env, timeout=45)    # limpieza COMPLETA antes de la siguiente prueba
    except subprocess.TimeoutExpired:
        meta["limpieza"] = "tiempo excedido (los residuos finales decidiran si se interrumpe la secuencia)"
    meta["fin_limpieza"] = clock().isoformat(timespec="milliseconds")
    seen = {json.loads(l).get("target") for l in logs.splitlines() if l.startswith("{") and json.loads(l).get("target")}
    meta["destinos_vistos_por_el_proxy"] = sorted(seen)
    meta["solo_destino_autorizado"] = seen <= {env["PROXY_ALLOW"]}
    meta["residuos_finales"] = residuals(env)
    meta["escaneo_de_secretos_en_evidencia"] = scan(d)
    meta["abort_global"] = (not meta["solo_destino_autorizado"]) or bool(meta["escaneo_de_secretos_en_evidencia"]) or sum(meta["residuos_finales"].values()) > 0
    (d / "run_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def run_sequence(tls_groups: str, base_dir: Path, start: dt.datetime, clock=lambda: dt.datetime.now(UTC), sleep=time.sleep, one=run_one) -> dict:
    """A1 y A2 en orden, ventana GLOBAL de 5 min. A2 se ejecuta aunque A1 sea GO (se comparan los destinos)."""
    latest, deadline = start + dt.timedelta(seconds=LATEST_START_S), start + dt.timedelta(seconds=WINDOW_S)
    meta = {"secuencia": [f"{l}={h}:{TARGETS[h]}" for l, h in SEQUENCE], "tls_groups": tls_groups, "ventana_inicio": start.isoformat(),
            "inicio_maximo": latest.isoformat(), "limite_duro_global": deadline.isoformat(), "pruebas": [],
            "nota_causalidad": "TLS_GROUPS=X25519 cambia el ClientHello (~517 B en lugar de ~1530 B): un resultado no permite atribuir causalmente al tamano el fallo anterior de relay.nsec.app."}
    while clock() < start:
        sleep(0.05)
    t0 = clock()
    meta["inicio_real"] = t0.isoformat(timespec="milliseconds")
    if t0 >= latest:
        meta["abortado"] = "inicio fuera de la ventana"
    else:
        for i, (label, host) in enumerate(SEQUENCE):
            remaining = (deadline - clock()).total_seconds()
            if i > 0 and remaining < MIN_NEXT_S:
                meta["pruebas"].append({"etiqueta": label, "destino": f"{host}:{TARGETS[host]}", "intentos": 0, "omitida": f"quedan {remaining:.0f} s (< {MIN_NEXT_S} s)"})
                break
            r = one(label, host, tls_groups, base_dir, deadline, clock)
            meta["pruebas"].append(r)
            if r.get("abort_global"):
                meta["secuencia_interrumpida_tras"] = label
                break
    t1 = clock()
    meta["fin"] = t1.isoformat(timespec="milliseconds")
    meta["duracion_total_s"] = round((t1 - t0).total_seconds(), 2)
    meta["dentro_de_la_ventana"] = t1 <= deadline
    meta["comparacion"] = {p["etiqueta"]: p.get("sonda") for p in meta["pruebas"]}
    base_dir.mkdir(parents=True, exist_ok=True)
    (base_dir / "run_meta_global.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["check", "check-b", "preflight", "preflight-b", "run"])
    ap.add_argument("--relay-host", default="relay.primal.net", choices=sorted(TARGETS), help="solo check/preflight; `run` usa SEQUENCE")
    ap.add_argument("--tls-groups", required=True, choices=["X25519", "default"], help="X25519 = ClientHello de ~517 B; default = como en la Compuerta A anterior (~1530 B)")
    ap.add_argument("--evidence-dir", default="lab/results/gate-a")
    ap.add_argument("--start", help="ISO 8601 con zona horaria, p. ej. 2026-11-21T17:00:00-03:00 (solo run)")
    a = ap.parse_args()
    evidence_dir = (ROOT / a.evidence_dir) if not Path(a.evidence_dir).is_absolute() else Path(a.evidence_dir)
    if "results" not in evidence_dir.parts:
        print("la evidencia debe ir bajo lab/results/ (excluido de Git)")
        return 2
    if a.mode == "run":
        if not a.start:
            print("run exige --start")
            return 2
        start = dt.datetime.fromisoformat(a.start)
        if start.tzinfo is None:
            print("--start debe llevar zona horaria")
            return 2
        print(json.dumps(run_sequence(a.tls_groups, evidence_dir, start), indent=2))
        return 0
    env = make_env(a.relay_host, a.tls_groups, evidence_dir)
    if a.mode == "check":
        chk = static_check(env)
        print(json.dumps(chk, indent=2))
        return 0 if all(v for k, v in chk.items() if k != "tls_groups") else 1
    if a.mode == "preflight-b":
        return preflight_b(evidence_dir, a.tls_groups)
    if a.mode == "check-b":
        env = make_env(GATE_B_RELAY, a.tls_groups, evidence_dir)                       # la Compuerta B no admite otro relay
        hostile = hostile_env(env)
        chk = static_check(hostile, COMPOSE_B)
        senv = json.loads(sh(COMPOSE_B + ["config", "--format", "json"], hostile).stdout)["services"]["signer"]["environment"]
        chk["MODE_efectivo"] = senv["MODE"]
        chk["APPROVAL_MODE_efectivo_con_entorno_hostil"] = senv["APPROVAL_MODE"]
        print(json.dumps(chk, indent=2))
        booleans = all(v for k, v in chk.items() if k not in ("tls_groups", "APPROVAL_MODE_efectivo_con_entorno_hostil", "MODE_efectivo"))
        return 0 if booleans and chk["MODE_efectivo"] == "observe" and chk["APPROVAL_MODE_efectivo_con_entorno_hostil"] == "tty" else 1
    return preflight(env, evidence_dir)


if __name__ == "__main__":
    sys.exit(main())
