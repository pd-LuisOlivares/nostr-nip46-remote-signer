#!/usr/bin/env python3
"""Orquestador del laboratorio NIP-46 (Fase 1.0A). Solo biblioteca estandar; se ejecuta en el HOST.

Para cada escenario levanta relay + firmante, espera a que el firmante este SUSCRITO (evento `ready`, tras
el EOSE del relay) y solo entonces lanza el cliente NDK real. Todo ocurre en la red `internal` del proyecto
Compose `nip46-lab`; la limpieza (`down -v`) afecta unicamente a ese proyecto.

Los criterios de aceptacion de cada experimento estan CODIFICADOS AQUI y se fijaron antes de ejecutar:
E1-E6 segun docs/stacker-news-compatibility.md §3.5; E7 segun la propuesta aprobada. No se ajustan segun resultados.
Veredictos: PASS, FAIL, BLOCKED, INCONCLUSIVE.
"""
import argparse
import datetime
import json
import os
import subprocess
import sys
import time
from pathlib import Path

LAB = Path(__file__).resolve().parent
BASE = ["docker", "compose", "-f", str(LAB / "compose.yaml"), "-p", "nip46-lab"]
RESULTS = LAB / "results"
E7_FAULTS = ["wrong_id", "error_field", "malformed_json", "garbage", "bad_mac", "spoof",
             "duplicate", "unknown_id_first", "auth_url", "get_pubkey_error", "mixed"]


def sh(args, env=None, timeout=300, stdin=None):
    return subprocess.run(args, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, input=stdin)


def compose(*args, env=None, timeout=300, stdin=None):
    return sh(BASE + list(args), env=env, timeout=timeout, stdin=stdin)


def parse(text):
    out = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def first(evs, name):
    return next((e for e in evs if e.get("ev") == name), None)


def all_ev(evs, name):
    return [e for e in evs if e.get("ev") == name]


# ------------------------------------------------------------------ ejecucion de escenarios
def run_scenario(spec):
    svc = "signer-ref" if spec["signer"] == "ref" else "signer-py"
    env = {**os.environ, "REPLY_MODE": spec["reply_mode"], "FAULT": spec.get("fault", "none"),
           "JITTER_MS": str(spec.get("jitter_ms", 0)), "SCENARIO": spec["scenario"],
           "TIMEOUT_MS": str(spec.get("timeout_ms", 15000)), "N_SIGN": str(spec.get("n_sign", 20)), "USE_SECRET": "1"}
    run = {"spec": spec, "errors": [], "client": [], "signer": [], "relay": [], "client_raw_tail": ""}
    t0 = time.time()
    try:
        compose("down", "-v", "--remove-orphans", env=env, timeout=120)
        up = compose("up", "-d", "relay", svc, env=env, timeout=240)
        if up.returncode:
            run["errors"].append("up fallo: " + up.stderr[-300:])
            run["blocked"] = True
            return run
        ready = None
        for _ in range(80):
            lg = compose("logs", "--no-color", "--no-log-prefix", svc, env=env)
            ready = first(parse(lg.stdout), "ready")
            if ready:
                break
            time.sleep(0.5)
        if not ready:
            run["errors"].append("el firmante no llego a `ready` en 40 s")
            run["signer"] = parse(compose("logs", "--no-color", "--no-log-prefix", svc, env=env).stdout)
            run["relay"] = parse(compose("logs", "--no-color", "--no-log-prefix", "relay", env=env).stdout)
            return run
        cl = compose("run", "--rm", "-T", "client", env=env, timeout=spec.get("timeout_ms", 15000) / 1000 + 90)
        run["client"] = parse(cl.stdout)
        run["client_raw_tail"] = (cl.stdout[-300:] if cl.returncode else "")
        if cl.returncode:
            run["errors"].append(f"cliente salio con codigo {cl.returncode}: {cl.stderr[-200:]}")
        run["signer"] = parse(compose("logs", "--no-color", "--no-log-prefix", svc, env=env).stdout)
        run["relay"] = parse(compose("logs", "--no-color", "--no-log-prefix", "relay", env=env).stdout)
    except subprocess.TimeoutExpired as exc:
        run["errors"].append(f"timeout del orquestador: {exc}")
    finally:
        compose("down", "-v", "--remove-orphans", env=env, timeout=120)
        run["duration_s"] = round(time.time() - t0, 2)
    return run


def facts(run):
    c, s, r = run["client"], run["signer"], run["relay"]
    st, rd = first(c, "start"), first(s, "ready")
    f = {"start": st, "ready": rd, "rr": first(c, "ready_result"), "login": first(c, "login_event"),
         "burst": first(c, "burst_result"), "parse": all_ev(c, "ndk_parse"), "enc": all_ev(c, "ndk_encrypt"),
         "dec": all_ev(c, "ndk_decrypt"), "unhandled": all_ev(c, "unhandled_rejection"),
         "authurl": all_ev(c, "authUrl"), "s_req": all_ev(s, "request"), "s_derr": all_ev(s, "decrypt_error"),
         "s_pub": all_ev(s, "response_published"), "s_sign": all_ev(s, "sign_event_ok"),
         "s_idmis": all_ev(s, "client_id_mismatch"), "req": [], "resp": [], "other": []}
    if st and rd:
        c8, t8 = st["client_pub8"], rd["transport_pub8"]
        frames = all_ev(r, "event_in")
        f["req"] = [x for x in frames if x["author"] == c8]
        f["resp"] = [x for x in frames if x["author"] == t8]
        f["other"] = [x for x in frames if x["author"] not in (c8, t8)]
        f["t8"], f["c8"] = t8, c8
    return f


def attribute(run, f):
    """Identifica DONDE esta el problema antes de atribuirlo al cifrado."""
    if run.get("blocked") or not f["ready"]:
        return "entorno/simulador: el firmante no estuvo listo o no pudo iniciarse"
    if not f["start"]:
        return "entorno/cliente: el cliente NDK no llego a iniciar"
    if not f["req"]:
        return "cliente NDK o relay: ninguna solicitud del cliente llego al relay"
    if f["s_derr"]:
        return "simulador: el firmante no pudo descifrar una solicitud (" + f["s_derr"][0].get("error", "?") + ")"
    if f["s_req"] and not f["resp"]:
        return "simulador: el firmante recibio la solicitud pero no publico respuesta"
    if f["resp"] and any(not p["ok"] for p in f["parse"]):
        return "NDK: no pudo procesar una respuesta que el relay entrego"
    if f["resp"] and not f["parse"]:
        return "relay o NDK: la respuesta se publico pero NDK no la proceso"
    return "sin atribucion clara: revisar evidencia cruda"


def schemes(frames):
    return [x["scheme"] for x in frames]


def transitions(f):
    return [(p["before"], p["after"]) for p in f["parse"] if p["before"] != p["after"]]


def ready_ok(f):
    rr = f["rr"]
    return bool(rr and rr["ok"] and rr["matches_identity"])


# ------------------------------------------------------------------ criterios por experimento
def evaluate(exp, run):
    f = facts(run)
    base = {"id": exp["id"], "objective": exp["objective"], "config": exp["config"],
            "expected": exp["expected"], "errors": run["errors"], "duration_s": run.get("duration_s")}
    if run.get("blocked"):
        return {**base, "verdict": "BLOCKED", "observed": {}, "attribution": attribute(run, f)}
    rr = f["rr"]
    obs = {"ready_result": ({k: rr[k] for k in ("ok", "matches_identity", "error", "ms", "encryption_type")} if rr else None),
           "request_schemes_relay": schemes(f["req"]), "response_schemes_relay": schemes(f["resp"]),
           "ndk_transitions": transitions(f), "ndk_decrypt_failures": [d.get("error") for d in f["dec"] if not d["ok"]],
           "ndk_parse_failures": [p.get("error") for p in f["parse"] if not p["ok"]],
           "signer_decrypt_errors": [d.get("error") for d in f["s_derr"]], "unhandled": [u["error"] for u in f["unhandled"]]}
    kind = exp["kind"]
    verdict, attribution = "INCONCLUSIVE", None
    sch_req, sch_resp = schemes(f["req"]), schemes(f["resp"])
    flip = ("nip04", "nip44") in transitions(f)
    if not rr:
        attribution = attribute(run, f)
    elif kind in ("e1", "e2"):
        exercised = bool(sch_req) and sch_req[0] == "nip04" and bool(sch_resp) and sch_resp[0] == "nip44"
        ok = ready_ok(f)
        if kind == "e2":
            lg = f["login"]
            obs["login_event"] = ({k: lg.get(k) for k in ("all_ok", "id_ok", "sig_ok", "tags0_ok", "pubkey_is_identity", "encryption_type", "error")} if lg else None)
            exercised = exercised and len(sch_req) >= 3
            ok = ok and bool(lg and lg.get("all_ok")) and sch_req[1:3] == ["nip44", "nip44"] and bool(f["s_sign"]) and not f["s_idmis"]
        if not exercised:
            verdict, attribution = "INCONCLUSIVE", "no se ejercito el escenario previsto (esquemas observados en el relay: " + str(sch_req[:3]) + " / " + str(sch_resp[:3]) + ")"
        elif ok and flip:
            verdict = "PASS"
        else:
            verdict, attribution = "FAIL", attribute(run, f)
    elif kind == "e4":
        allf = f["req"] + f["resp"]
        lg = f["login"]
        obs["login_event"] = ({k: lg.get(k) for k in ("all_ok", "encryption_type", "error")} if lg else None)
        exercised = len(f["req"]) >= 3 and len(f["resp"]) >= 3
        ok = ready_ok(f) and bool(lg and lg.get("all_ok")) and all(x["scheme"] == "nip04" for x in allf) \
            and all(p["before"] == "nip04" and p["after"] == "nip04" for p in f["parse"])
        verdict = "PASS" if (exercised and ok) else ("INCONCLUSIVE" if not exercised else "FAIL")
        attribution = None if verdict == "PASS" else (attribute(run, f) if verdict == "FAIL" else "escenario incompleto")
    elif kind == "e6":
        b = f["burst"]
        obs["burst"] = b
        n = run["spec"].get("n_sign", 20)
        exercised = len(f["req"]) >= 2 + n
        ok = (ready_ok(f) and bool(b) and b["fulfilled"] == n and b["all_ok"] == n and len(transitions(f)) <= 1
              and not f["unhandled"] and not f["s_derr"] and (not transitions(f) or transitions(f)[0] == ("nip04", "nip44")))
        verdict = "PASS" if (exercised and ok) else ("INCONCLUSIVE" if not exercised else "FAIL")
        attribution = None if verdict == "PASS" else (attribute(run, f) if verdict == "FAIL" else "escenario incompleto")
    elif kind == "e3":
        sh_client = sorted(e["plaintext_sha256"] for e in f["enc"])
        sh_signer = sorted(e["plaintext_sha256"] for e in f["s_req"])
        connect_ok = bool(f["s_req"]) and f["s_req"][0]["method"] == "connect" and f["s_req"][0]["scheme"] == "nip04"
        obs["plaintext_hashes_equal"] = sh_client == sh_signer and bool(sh_client)
        obs["first_request_nip04_connect_decrypted_by_python"] = connect_ok
        ok = obs["plaintext_hashes_equal"] and connect_ok and not f["s_derr"] and ready_ok(f)
        verdict = "PASS" if ok else ("INCONCLUSIVE" if not f["s_req"] else "FAIL")
        attribution = None if verdict == "PASS" else attribute(run, f)
    elif kind == "e7":
        verdict, attribution = evaluate_e7(exp["fault"], run, f, obs)
    return {**base, "verdict": verdict, "observed": obs, "attribution": attribution,
            "versions": (f["start"] or {}).get("versions")}


def evaluate_e7(fault, run, f, obs):
    rr = f["rr"]
    pub = {x["label"] for x in f["s_pub"]}
    marker = {"wrong_id": "wrong_id", "error_field": "error_field", "malformed_json": "malformed_json", "garbage": "garbage",
              "bad_mac": "bad_mac", "spoof": "spoofed_by_other_key", "duplicate": "duplicate_2", "unknown_id_first": "unknown_id",
              "auth_url": "auth_url", "get_pubkey_error": "get_pubkey_error"}.get(fault)
    if fault == "mixed":
        exercised = len({x["scheme"] for x in f["s_pub"]}) >= 2
    else:
        exercised = marker in pub
    if not exercised:
        return "INCONCLUSIVE", f"el fallo `{fault}` no llego a inyectarse (publicaciones: {sorted(pub)})"
    ms = rr["ms"] if rr else None
    parse_fail = [p for p in f["parse"] if not p["ok"]]
    dec_fail = [d for d in f["dec"] if not d["ok"]]
    ok_parse = [p for p in f["parse"] if p["ok"]]
    obs["authUrl_events"] = [a["url"] for a in f["authurl"]]
    obs["parse_ok_count"] = len(ok_parse)
    obs["spoof_accepted_author8"] = [p["author8"] for p in f["parse"] if p.get("ok") and f.get("t8") and p["author8"] != f["t8"]]
    if fault == "wrong_id":
        ok = ready_ok(f) and ms >= 1400
    elif fault == "error_field":
        ok = bool(rr) and not rr["ok"] and rr["error"] == "lab-denied" and ms < 5000
    elif fault == "malformed_json":
        ok = ready_ok(f) and ms >= 1400 and any("JSON" in str(p.get("error")) or "Unexpected" in str(p.get("error")) for p in parse_fail)
    elif fault == "garbage":
        ok = ready_ok(f) and ms >= 1400 and len(parse_fail) >= 1
    elif fault == "bad_mac":
        ok = ready_ok(f) and ms >= 1400 and any("MAC" in str(d.get("error")) for d in dec_fail)
    elif fault == "spoof":
        ok = ready_ok(f) and bool(obs["spoof_accepted_author8"])
    elif fault == "duplicate":
        ok = ready_ok(f) and len(ok_parse) >= 3 and not f["unhandled"]
    elif fault == "unknown_id_first":
        ok = ready_ok(f) and ms < 5000 and len({p.get("req_id") for p in ok_parse}) >= 3
    elif fault == "auth_url":
        ok = ready_ok(f) and any("lab.invalid" in a["url"] for a in f["authurl"]) and ms >= 900
    elif fault == "get_pubkey_error":
        ok = bool(rr) and rr["ok"] and not rr["matches_identity"] and rr["error"] is None and rr["user_pub_type"] != "string"
    elif fault == "mixed":
        ok = ready_ok(f) and len(transitions(f)) >= 2
    else:
        ok = False
    return ("PASS", None) if ok else ("FAIL", attribute(run, f))


# ------------------------------------------------------------------ otras etapas
def run_units():
    t0 = time.time()
    p = compose("run", "--rm", "-T", "-e", "LAB_QUIET=1", "py-job", "python", "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-v", timeout=600)
    compose("down", "-v", "--remove-orphans", timeout=120)
    tail = (p.stderr or "")[-400:]
    import re
    m = re.search(r"Ran (\d+) tests? in", p.stderr or "")
    passed = p.returncode == 0 and "OK" in tail
    names = [ln.split(" ... ")[0] for ln in (p.stderr or "").splitlines() if " ... ok" in ln]
    return {"id": "E0", "objective": "Pruebas propias: relay NIP-01, vectores oficiales NIP-44 (validos e invalidos), NIP-04",
            "config": {"runner": "unittest en contenedor py-job"}, "expected": "todas las pruebas aprobadas",
            "observed": {"tests_ran": int(m.group(1)) if m else None, "returncode": p.returncode, "ok_tests": len(names)},
            "duration_s": round(time.time() - t0, 2), "errors": [] if passed else [tail],
            "verdict": "PASS" if passed else "FAIL", "attribution": None if passed else "revisar la salida de unittest"}


def run_e5():
    t0 = time.time()
    errors, res = [], {}
    a = compose("run", "--rm", "-T", "node-job", "node", "client/xtest.mjs", "encrypt", timeout=300)
    b = compose("run", "--rm", "-T", "py-job", "python", "xtest.py", stdin=a.stdout, timeout=300) if a.returncode == 0 else None
    c = compose("run", "--rm", "-T", "node-job", "node", "client/xtest.mjs", "decrypt", stdin=b.stdout, timeout=300) if b and b.returncode == 0 else None
    compose("down", "-v", "--remove-orphans", timeout=120)
    if not (a.returncode == 0 and b and b.returncode == 0 and c and c.returncode == 0):
        errors.append("fallo de ejecucion: " + " | ".join(x.stderr[-150:] for x in (a, b, c) if x is not None and x.returncode))
        return [{"id": i, "objective": o, "config": {}, "expected": "", "observed": {}, "errors": errors, "duration_s": round(time.time() - t0, 2),
                 "verdict": "BLOCKED", "attribution": "entorno"} for i, o in (("E5", "NIP-44 cruzado"), ("E5b", "NIP-04 cruzado"))]
    py_dec = json.loads(b.stdout)["decrypted_nostr_tools_payloads"]
    nt_dec = json.loads(c.stdout)["decrypted_python_payloads"]
    out = []
    for eid, scheme, obj in (("E5", "nip44", "NIP-44 cruzado: nostr-tools cifra/Python descifra y al reves (1, 32, 33, 1000 B, Unicode, 65535 B)"),
                             ("E5b", "nip04", "COMPLEMENTO no definido en la Fase 0.3: NIP-04 cruzado con los mismos mensajes")):
        p_ok = {x["name"]: x["ok"] for x in py_dec if x["scheme"] == scheme}
        n_ok = {x["name"]: x["ok"] for x in nt_dec if x["scheme"] == scheme}
        allok = bool(p_ok) and all(p_ok.values()) and all(n_ok.values()) and len(p_ok) == len(n_ok)
        out.append({"id": eid, "objective": obj, "config": {"sentidos": "nostr-tools->Python y Python->nostr-tools", "claves": "juguete fijas publicas"},
                    "expected": "resultados identicos en ambos sentidos",
                    "observed": {"python_descifra_payloads_de_nostr_tools": p_ok, "nostr_tools_descifra_payloads_de_python": n_ok},
                    "errors": [], "duration_s": round(time.time() - t0, 2), "verdict": "PASS" if allok else "FAIL",
                    "attribution": None if allok else "ver mensajes que fallan en observed"})
    return out


def verify_isolation():
    env = {**os.environ, "REPLY_MODE": "nip44", "FAULT": "none"}
    compose("down", "-v", "--remove-orphans", env=env, timeout=120)
    compose("up", "-d", "relay", env=env, timeout=240)
    checks = {}
    net = sh(["docker", "network", "inspect", "nip46-lab_lab_net", "--format", "{{json .Internal}}"]).stdout.strip()
    checks["red_internal"] = net == "true"
    cid = compose("ps", "-q", "relay").stdout.strip()
    insp = json.loads(sh(["docker", "inspect", cid]).stdout)[0]
    hc = insp["HostConfig"]
    checks["sin_puertos_publicados"] = not any(insp["NetworkSettings"].get("Ports", {}).values()) and not hc.get("PortBindings")
    checks["rootfs_solo_lectura"] = bool(hc.get("ReadonlyRootfs"))
    checks["cap_drop_all"] = hc.get("CapDrop") == ["ALL"]
    checks["no_new_privileges"] = "no-new-privileges:true" in (hc.get("SecurityOpt") or [])
    checks["no_privilegiado"] = not hc.get("Privileged")
    probe = ("import json,os\n"
             "st=dict(l.split(':',1) for l in open('/proc/self/status').read().splitlines() if ':' in l)\n"
             "routes=[l.split()[1] for l in open('/proc/net/route').read().splitlines()[1:]]\n"
             "try:\n    open('/lab/escritura-prueba','w').close(); w=True\nexcept OSError:\n    w=False\n"
             "print(json.dumps({'uid':os.getuid(),'cap_eff':st['CapEff'].strip(),'nonewprivs':st['NoNewPrivs'].strip(),'tiene_ruta_por_defecto':'00000000' in routes,'puede_escribir_rootfs':w}))")
    pr = json.loads(compose("exec", "-T", "relay", "python", "-c", probe, env=env).stdout.strip().splitlines()[-1])
    checks["dentro_del_contenedor"] = pr
    checks["usuario_no_root"] = pr["uid"] != 0
    checks["sin_capacidades_efectivas"] = set(pr["cap_eff"]) <= {"0"}
    checks["sin_ruta_por_defecto"] = pr["tiene_ruta_por_defecto"] is False
    checks["no_puede_escribir_rootfs"] = pr["puede_escribir_rootfs"] is False
    compose("down", "-v", "--remove-orphans", env=env, timeout=120)
    all_ok = all(v for k, v in checks.items() if k != "dentro_del_contenedor")
    return {"id": "AISL", "objective": "Verificacion de aislamiento (red internal, sin puertos, endurecimiento)", "config": {},
            "expected": "todas las comprobaciones verdaderas", "observed": checks, "errors": [], "duration_s": None,
            "verdict": "PASS" if all_ok else "FAIL", "attribution": None if all_ok else "ver observed"}


def environment_info():
    probe = ("import sys,json,importlib.metadata as m;print(json.dumps({'python':sys.version.split()[0],"
             "**{p:m.version(p) for p in ('coincurve','cryptography','cffi','pycparser','websockets')}}))")
    py = json.loads(compose("run", "--rm", "-T", "py-job", "python", "-c", probe).stdout.strip().splitlines()[-1])
    compose("down", "-v", "--remove-orphans", timeout=120)
    imgs = {}
    for name in ("nip46-lab-py:1.0a", "nip46-lab-node:1.0a"):
        imgs[name] = sh(["docker", "image", "inspect", name, "--format", "{{.Id}} {{.Os}}/{{.Architecture}}"]).stdout.strip()
    return {"python_side": py, "images": imgs,
            "base_digests": {"node": "sha256:e9f565d32859f0cbfb52125eafe8be39390f24dac302dc3cdf566e8ba3ab21ee",
                             "python": "sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b"}}


# ------------------------------------------------------------------ ensayo general local E8-E10 (Fase 1.0A.2)
# Firmante REAL minimo (lab_real) + proxy de salida + NDK 2.12.2 + relay local. SIN conexiones externas.
# Criterios fijados en lab/experiments/definitions-real.md ANTES de ejecutar; no se ajustan segun resultados.
import re
import tempfile

REH = ["docker", "compose", "-f", str(LAB / "real" / "compose.real.yaml"), "-f", str(LAB / "real" / "compose.rehearsal.yaml"), "-p", "nip46-rehearsal"]
REH_NET = "nip46-rehearsal_real_internal"
E8_EXPECT = {"wrong_origin": "origen", "wrong_content": "content", "wrong_method": "metodo", "extra_tag": "estructura",
             "wrong_kind": "kind", "stale": "created_at", "future": "created_at", "bad_challenge": "challenge",
             "tag_order": "estructura", "replay_same_challenge": "reutilizacion"}
E9_EXPECT = [(False, "humano"), (False, "timeout"), (True, "humano"), (True, "humano"), (False, "tope")]


def reh(*args, env=None, timeout=300, stdin=None):
    return sh(REH + list(args), env=env, timeout=timeout, stdin=stdin)


def jsonl(path):
    p = Path(path)
    return parse(p.read_text(encoding="utf-8")) if p.exists() else []


def reh_session(scenario, script, out_dir, timeout_s=3, extra=None, hook=None, client_timeout=240):
    """Levanta relay-lab + proxy + firmante REAL, espera a que emita la URI, ejecuta el cliente NDK y recoge todo."""
    out_dir.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PROXY_ALLOW": "relay-lab:7777", "RELAY_URL": "ws://relay-lab:7777", "SN_ORIGIN": "https://sn.lab.invalid",
           "EVIDENCE_DIR": str(out_dir), "MODE": "sign", "APPROVAL_MODE": "scripted", "APPROVAL_SCRIPT": script,
           "APPROVAL_TIMEOUT_S": str(timeout_s), "URI_FILE": "/ctl/bunker.txt", "SCENARIO": scenario, **(extra or {})}
    run = {"scenario": scenario, "errors": [], "client": [], "evidence": [], "proxy": [], "relay": [], "hook": None, "raw_client": ""}
    try:
        reh("down", "-v", "--remove-orphans", env=env, timeout=120)
        (out_dir / "evidence.jsonl").unlink(missing_ok=True)
        up = reh("up", "-d", "relay-lab", "proxy", "signer", env=env, timeout=300)
        if up.returncode:
            run["errors"].append("up fallo: " + up.stderr[-300:])
            run["blocked"] = True
            return run
        for _ in range(80):
            if any(e["ev"] == "bunker_issued" for e in jsonl(out_dir / "evidence.jsonl")):
                break
            time.sleep(0.5)
        else:
            run["errors"].append("el firmante no emitio la URI en 40 s")
            run["blocked"] = True
            return run
        cl = reh("run", "--rm", "-T", "client", env=env, timeout=client_timeout)
        run["client"], run["raw_client"] = parse(cl.stdout), cl.stdout
        if cl.returncode:
            run["errors"].append(f"cliente salio con codigo {cl.returncode}: {cl.stderr[-200:]}")
        if hook:
            run["hook"] = hook(env, out_dir)
        run["evidence"] = jsonl(out_dir / "evidence.jsonl")
        run["proxy"] = parse(reh("logs", "--no-color", "--no-log-prefix", "proxy", env=env).stdout)
        run["relay"] = parse(reh("logs", "--no-color", "--no-log-prefix", "relay-lab", env=env).stdout)
    except subprocess.TimeoutExpired as exc:
        run["errors"].append(f"timeout del orquestador: {exc}")
    finally:
        reh("down", "-v", "--remove-orphans", env=env, timeout=120)
    return run


def variants(run):
    return [e for e in run["client"] if e.get("ev") == "variant"]


def ev_of(run, name):
    return [e for e in run["evidence"] if e.get("ev") == name]


def sign_decisions(run):
    return [(d["approved"], d["reason"]) for d in ev_of(run, "decision") if d["kind"] == "sign_event"]


def client_ready(run):
    rr = first(run["client"], "ready_result")
    return bool(rr and rr["ok"] and rr["matches_identity"])


def eval_e8(run):
    v, pol = variants(run), ev_of(run, "policy")
    labels = [x["label"] for x in v]
    expected_labels = list(E8_EXPECT)[:9] + ["valid", "replay_same_challenge"]
    obs = {"labels": labels, "signed": {x["label"]: x["signed"] for x in v}, "policy_ok": [p["ok"] for p in pol],
           "policy_failed": [p["failed"] for p in pol], "sign_decisions": sign_decisions(run), "sign_ok_events": len(ev_of(run, "sign_ok"))}
    if labels != expected_labels or len(pol) != len(expected_labels):
        return "INCONCLUSIVE", obs, "no se ejercitaron las 11 solicitudes previstas"
    good = next(x for x in v if x["label"] == "valid")
    checks = {
        "cliente_listo": client_ready(run),
        "invalidas_no_firmadas": all(not x["signed"] for x in v if x["label"] != "valid"),
        "cada_rechazo_por_su_comprobacion": all(E8_EXPECT[x["label"]] in p["failed"] for x, p in zip(v, pol) if x["label"] != "valid"),
        "valida_firmada_y_verificada": bool(good["signed"] and good["id_ok"] and good["sig_ok"] and good["pubkey_is_identity"]
                                           and good["tags_n"] == 3 and good["tags_unchanged"]),
        "valida_pasa_las_comprobaciones": pol[9]["ok"] is True and pol[9]["failed"] == [],
        "una_sola_pregunta_de_firma": sign_decisions(run) == [(True, "humano")],
        "una_sola_firma": len(ev_of(run, "sign_ok")) == 1 and ev_of(run, "sign_ok")[0]["self_verify"] is True,
    }
    obs["checks"] = checks
    return ("PASS" if all(checks.values()) else "FAIL"), obs, None if all(checks.values()) else "ver checks"


def eval_e9(run):
    v = variants(run)
    obs = {"signed": [x["signed"] for x in v], "ms": [x["ms"] for x in v], "sign_decisions": sign_decisions(run),
           "sign_ok_events": len(ev_of(run, "sign_ok")), "errors": [x.get("error") for x in v]}
    if len(v) != 5 or len(sign_decisions(run)) != 5:
        return "INCONCLUSIVE", obs, "no se ejercitaron las 5 solicitudes previstas"
    c, d = v[2], v[3]
    checks = {
        "cliente_listo": client_ready(run),
        "denegada_timeout_y_tope_no_firman": [x["signed"] for x in v] == [False, False, True, True, False],
        "decisiones_en_orden": obs["sign_decisions"] == E9_EXPECT,
        "dos_firmas_validas": all(x["id_ok"] and x["sig_ok"] and x["pubkey_is_identity"] for x in (c, d)) and obs["sign_ok_events"] == 2,
        "el_timeout_espero_la_aprobacion": v[1]["ms"] >= 2500,
    }
    obs["checks"] = checks
    return ("PASS" if all(checks.values()) else "FAIL"), obs, None if all(checks.values()) else "ver checks"


def eval_e9c(run):
    rr = first(run["client"], "ready_result")
    dec = [(d["kind"], d["approved"], d["reason"]) for d in ev_of(run, "decision")]
    obs = {"ready_result": rr and {k: rr[k] for k in ("ok", "error", "ms")}, "decisions": dec, "policy_events": len(ev_of(run, "policy")),
           "sign_ok_events": len(ev_of(run, "sign_ok")), "get_public_key_answered": any(e.get("method") == "get_public_key" for e in ev_of(run, "request"))}
    if not rr:
        return "INCONCLUSIVE", obs, "el cliente no llego a ready_result"
    checks = {"cliente_no_conectado": rr["ok"] is False, "connect_denegado_por_defecto": dec == [("connect", False, "humano")] or dec == [("connect", False, "timeout")],
              "ninguna_firma_ni_politica": obs["policy_events"] == 0 and obs["sign_ok_events"] == 0}
    obs["checks"] = checks
    return ("PASS" if all(checks.values()) else "FAIL"), obs, None if all(checks.values()) else "ver checks"


E11_LABELS = ["wrong_origin", "wrong_content", "wrong_method", "extra_tag", "wrong_kind", "stale", "future", "bad_challenge", "tag_order",
              "valid", "replay_same_challenge"]


def eval_e11(run):
    """Compuerta B en ensayo: MODE=observe con un aprobador que dice si a todo. Criterios en definitions-real.md (E11)."""
    v, obs_sign = variants(run), ev_of(run, "observed_sign")
    labels = [x["label"] for x in v]
    decisions = [d for d in ev_of(run, "decision") if d["kind"] == "sign_event"]
    methods = [r["method"] for r in ev_of(run, "observed_request")]
    obs = {"labels": labels, "signed": {x["label"]: x["signed"] for x in v}, "n_observed_sign": len(obs_sign),
           "sign_decisions": sign_decisions(run), "methods": {m: methods.count(m) for m in sorted(set(methods))},
           "sign_ok_events": len(ev_of(run, "sign_ok")), "policy_events": len(ev_of(run, "policy"))}
    if labels != E11_LABELS or len(obs_sign) != 11:
        return "INCONCLUSIVE", obs, "no se ejercitaron/observaron las 11 solicitudes previstas"

    def structure_ok():
        for label, o in zip(labels, obs_sign):
            age = o["created_at_age_s"]
            age_ok = (595 <= age <= 620) if label == "stale" else (-65 <= age <= -55) if label == "future" else (-5 <= age <= 10)
            if not (o["u_seen"] == ("https://evil.invalid" if label == "wrong_origin" else "https://sn.lab.invalid")
                    and o["n_tags"] == (4 if label in ("extra_tag", "wrong_kind") else 3) and o["kind"] == (1 if label == "wrong_kind" else 27235)
                    and o["method_seen"] == ("POST" if label == "wrong_method" else "GET")
                    and o["content_seen"] == ("otro texto" if label == "wrong_content" else "Stacker News Authentication")
                    and o["challenge_shape"] == ("otro" if label == "bad_challenge" else "hex64") and age_ok
                    and (label != "tag_order" or o["tags"][0][0] == "u")):
                return False
        return obs_sign[9]["challenge_sha16"] == obs_sign[10]["challenge_sha16"] is not None

    own_text = json.dumps(run["evidence"]) + json.dumps(run["proxy"])        # el relay de laboratorio registra ids y claves PUBLICAS (64 hex)
    evidence_text = own_text + json.dumps(run["relay"])
    challenges = [x["k1"] for x in v if x.get("k1")]
    checks = {
        "cliente_listo": client_ready(run),
        "ninguna_firmada_ni_la_valida": all(not x["signed"] for x in v),
        "cero_sign_ok_ni_politica": not ev_of(run, "sign_ok") and not ev_of(run, "policy"),
        "decisiones_todas_modo_observacion": len(decisions) == 11 and all((d["approved"], d["reason"]) == (False, "modo_observacion") for d in decisions),
        "estructura_observada_coincide": structure_ok(),
        "metodos_observados": methods.count("sign_event") == 11 and "connect" in methods and "get_public_key" in methods,
        "sin_secretos_ni_retos_en_claro": not any(c in evidence_text for c in challenges) and not re.search(r"bunker://|secret=|nsec1", evidence_text)
                                        and not re.search(r"[0-9a-fA-F]{64}", own_text),
    }
    obs["checks"] = checks
    return ("PASS" if all(checks.values()) else "FAIL"), obs, None if all(checks.values()) else [k for k, ok in checks.items() if not ok]


E11_CONTROLS = {
    "valida_firmada": ("ninguna_firmada_ni_la_valida", lambda r: r["client"].__setitem__(slice(None), [({**x, "signed": True} if x.get("ev") == "variant" and x["label"] == "valid" else x) for x in r["client"]])),
    "sign_ok_inyectado": ("cero_sign_ok_ni_politica", lambda r: r["evidence"].append({"ev": "sign_ok", "event_id16": "0" * 16, "tags0": "challenge", "self_verify": True})),
    "secreto_en_el_relay": ("sin_secretos_ni_retos_en_claro", lambda r: r["relay"].append({"ev": "x", "linea": "bunker://abc"})),
    "hex64_en_la_evidencia": ("sin_secretos_ni_retos_en_claro", lambda r: r["evidence"].append({"ev": "x", "valor": "a" * 64})),
}


ISOLATION_PROBE = r"""
import json, socket, sys
def tcp(host, port):
    try:
        socket.create_connection((host, port), 2).close(); return "conecta"
    except socket.gaierror: return "no_resuelve"
    except OSError as e: return type(e).__name__
def connect_via_proxy(target):
    s = socket.create_connection(("proxy", 3128), 3)
    s.sendall(f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n".encode())
    status = s.recv(64).split(b"\r\n")[0].decode("latin-1"); s.close(); return status
routes = [l.split()[1] for l in open("/proc/net/route").read().splitlines()[1:]]
st = dict(l.split(":", 1) for l in open("/proc/self/status").read().splitlines() if ":" in l)
try:
    open("/lab/py/x", "w").close(); w = True
except OSError: w = False
import os
print(json.dumps({"relay_directo": tcp("relay-lab", 7777), "proxy_alcanzable": tcp("proxy", 3128),
  "doc_testnet": tcp("192.0.2.1", 443), "ruta_por_defecto": "00000000" in routes, "uid": os.getuid(),
  "cap_eff": st["CapEff"].strip(), "no_new_privs": st["NoNewPrivs"].strip(), "escribe_rootfs": w,
  "tmp": sorted(os.listdir("/tmp")), "ctl": sorted(os.listdir("/ctl")),
  "connect_permitido": connect_via_proxy("relay-lab:7777"), "connect_otro_host": connect_via_proxy("example.com:443"),
  "connect_otro_puerto": connect_via_proxy("relay-lab:7778"), "connect_otro_host_misma_red": connect_via_proxy("proxy:3128")}))
"""


def e10_hook(env, out_dir):
    h = {}
    iso = reh("exec", "-T", "signer", "python", "-c", ISOLATION_PROBE, env=env)
    h["isolation_raw_ok"] = iso.returncode == 0
    h["isolation"] = json.loads(iso.stdout.strip().splitlines()[-1]) if iso.returncode == 0 and iso.stdout.strip() else {"error": iso.stderr[-300:]}
    pr = reh("run", "--rm", "-T", "signer", "python", "-m", "lab_real.probe", env=env, timeout=120)
    h["probe"] = json.loads(pr.stdout.strip().splitlines()[-1]) if pr.stdout.strip().startswith("{") else {"error": (pr.stdout + pr.stderr)[-300:]}
    ids = {}
    for svc in ("proxy", "signer", "relay-lab", "client"):
        cid = reh("ps", "-aq", svc, env=env).stdout.strip().splitlines()
        if cid:
            ids[svc] = json.loads(sh(["docker", "inspect", cid[0]]).stdout)[0]
    h["inspect"] = {}
    for svc, i in ids.items():
        hc = i["HostConfig"]
        h["inspect"][svc] = {"redes": sorted(i["NetworkSettings"]["Networks"]), "puertos": bool(hc.get("PortBindings")) or any(i["NetworkSettings"].get("Ports", {}).values()),
                             "ro": bool(hc.get("ReadonlyRootfs")), "cap_drop": hc.get("CapDrop"), "nnp": "no-new-privileges:true" in (hc.get("SecurityOpt") or []),
                             "privileged": bool(hc.get("Privileged")), "log_driver": hc["LogConfig"]["Type"],
                             "env_names": sorted(x.split("=", 1)[0] for x in i["Config"]["Env"]), "user": i["Config"]["User"]}
    h["nets_internal"] = {n: json.loads(sh(["docker", "network", "inspect", n, "--format", "{{json .Internal}}"]).stdout.strip() or "null")
                          for n in ("nip46-rehearsal_real_internal", "nip46-rehearsal_real_egress")}
    lg = reh("logs", "--no-color", "--no-log-prefix", "signer", env=env)
    h["signer_logs_stdout_len"] = len(lg.stdout.strip())
    h["signer_logs_stderr"] = lg.stderr.strip()[:160]
    tok = reh("exec", "-T", "signer", "python", "-c", "print(open('/ctl/bunker.txt').read().strip())", env=env).stdout.strip()
    m = re.search(r"secret=([A-Za-z0-9_-]+)", tok)
    h["secret_len"] = len(m.group(1)) if m else 0
    h["_secret"] = m.group(1) if m else ""
    reh("kill", "-s", "SIGINT", "signer", env=env)
    time.sleep(4)
    h["after_sigint_evidence_tail"] = [e["ev"] + ":" + str(e.get("reason", "")) for e in jsonl(out_dir / "evidence.jsonl")[-2:]]
    return h


def eval_e10(run, out_dir):
    h = run.get("hook") or {}
    iso, ins = h.get("isolation", {}), h.get("inspect", {})
    lg, rr = first(run["client"], "login_event"), first(run["client"], "ready_result")
    pxy_ok = [p for p in run["proxy"] if p.get("ev") == "connect_allowed"]
    pxy_den = [p for p in run["proxy"] if p.get("ev") == "connect_denied"]
    bi = first(run["evidence"], "bunker_issued")
    t8 = bi["transport_pub8"] if bi else None
    frames = [x for x in run["relay"] if x.get("ev") == "event_in"]
    resp_schemes = [x["scheme"] for x in frames if x.get("author") == t8]
    req_schemes = [x["scheme"] for x in frames if x.get("author") != t8]
    text_all = "\n".join([json.dumps(run["evidence"]), run["raw_client"], json.dumps(run["proxy"]), json.dumps(run["relay"]), json.dumps(h.get("probe", {}))])
    secret = h.get("_secret", "")
    evidence_text = (out_dir / "evidence.jsonl").read_text(encoding="utf-8") if (out_dir / "evidence.jsonl").exists() else ""
    obs = {"ready_result": rr and {k: rr[k] for k in ("ok", "matches_identity", "encryption_type")}, "login_event": lg and {k: lg.get(k) for k in ("all_ok", "id_ok", "sig_ok", "tags0_ok", "pubkey_is_identity")},
           "request_schemes_on_relay": req_schemes, "response_schemes_on_relay": resp_schemes, "proxy_allowed": [p["target"] for p in pxy_ok],
           "proxy_denied": [p.get("target") or p.get("linea") for p in pxy_den], "isolation": {k: v for k, v in iso.items()},
           "probe": h.get("probe"), "inspect": ins, "nets_internal": h.get("nets_internal"), "signer_logs_stdout_len": h.get("signer_logs_stdout_len"),
           "signer_logs_stderr": h.get("signer_logs_stderr"), "after_sigint_evidence_tail": h.get("after_sigint_evidence_tail")}
    if not (rr and h.get("isolation_raw_ok")):
        return "INCONCLUSIVE", obs, "el ciclo o la sonda de aislamiento no se ejecutaron"
    checks = {
        "ciclo_completo_con_firma_valida": client_ready(run) and bool(lg and lg.get("all_ok")),
        "respuestas_del_firmante_solo_nip44": bool(resp_schemes) and set(resp_schemes) == {"nip44"},
        "trafico_por_el_proxy": any(t == "relay-lab:7777" for t in obs["proxy_allowed"]) and len(pxy_ok) >= 1,
        "sin_acceso_directo_al_relay": iso.get("relay_directo") == "no_resuelve",
        "sin_ruta_por_defecto": iso.get("ruta_por_defecto") is False,
        "sin_salida_a_destino_no_permitido": iso.get("doc_testnet") != "conecta",
        "proxy_solo_permite_el_destino_configurado": iso.get("connect_permitido", "").split(" ")[1:2] == ["200"]
            and all(iso.get(k, "").split(" ")[1:2] == ["403"] for k in ("connect_otro_host", "connect_otro_puerto", "connect_otro_host_misma_red")),
        "rechazos_registrados_en_el_proxy": sorted(p.get("target") for p in pxy_den if p.get("reason") == "destino fuera de la lista blanca")
            == ["example.com:443", "proxy:3128", "relay-lab:7778"],
        "sin_ruido_en_el_proxy": all(p.get("reason") == "destino fuera de la lista blanca" for p in pxy_den),
        "firmante_solo_en_red_interna": ins.get("signer", {}).get("redes") == [REH_NET] and h.get("nets_internal", {}).get(REH_NET) is True,
        "proxy_en_ambas_redes": len(ins.get("proxy", {}).get("redes", [])) == 2,
        "sin_puertos_publicados": all(not ins.get(s, {}).get("puertos", True) for s in ("signer", "proxy", "relay-lab")),
        "endurecimiento": all(ins.get(s, {}).get("ro") and ins.get(s, {}).get("cap_drop") == ["ALL"] and ins.get(s, {}).get("nnp") and not ins.get(s, {}).get("privileged") for s in ("signer", "proxy")),
        "no_root_y_sin_capacidades": iso.get("uid") != 0 and set(iso.get("cap_eff", "x")) <= {"0"} and iso.get("no_new_privs") == "1" and iso.get("escribe_rootfs") is False,
        "logging_none_sin_salida_conservada": ins.get("signer", {}).get("log_driver") == "none" and h.get("signer_logs_stdout_len") == 0,
        # GPG_KEY es una variable de la imagen base de Python (huella PUBLICA para verificar CPython): no es un secreto.
        "sin_variables_con_forma_de_secreto": not any(re.search(r"KEY|SECRET|TOKEN|NSEC|PASS", n, re.I) for n in ins.get("signer", {}).get("env_names", ["KEY"]) if n != "GPG_KEY"),
        "sonda_del_relay_por_el_proxy_GO": (h.get("probe") or {}).get("verdict") == "GO",
        "interruptor_de_emergencia": h.get("after_sigint_evidence_tail", [""])[-1:] == ["session_end:interruptor_de_emergencia"],
        "secreto_de_la_uri_ausente_de_toda_la_evidencia": len(secret) >= 20 and secret not in text_all and "bunker://" not in text_all and "nsec1" not in text_all,
        "evidencia_sin_hex64": not re.search(r"\b[0-9a-f]{64}\b", evidence_text) and not re.search(r"\b[0-9a-f]{64}\b", json.dumps(run["proxy"])),
        "tmp_vacio_y_ctl_solo_ensayo": iso.get("tmp") == [] and set(iso.get("ctl", [])) == {"bunker.txt", "identity.txt"},
    }
    obs["checks"] = checks
    return ("PASS" if all(checks.values()) else "FAIL"), obs, None if all(checks.values()) else [k for k, v in checks.items() if not v]


E10_CONTROLS = {   # (alteracion sobre una copia del crudo de E10) -> comprobacion que DEBE fallar
    "relay_directo_conecta": ("sin_acceso_directo_al_relay", lambda r: r["hook"]["isolation"].update(relay_directo="conecta")),
    "ruido_en_el_proxy": ("sin_ruido_en_el_proxy", lambda r: r["proxy"].append({"ev": "connect_denied", "reason": "peticion incompleta o demasiado grande"})),
    "secreto_en_la_salida_del_cliente": ("secreto_de_la_uri_ausente_de_toda_la_evidencia", lambda r: r.update(raw_client=r["raw_client"] + r["hook"]["_secret"])),
    "log_driver_json": ("logging_none_sin_salida_conservada", lambda r: r["hook"]["inspect"]["signer"].update(log_driver="json-file")),
    "puertos_publicados": ("sin_puertos_publicados", lambda r: r["hook"]["inspect"]["signer"].update(puertos=True)),
    "variable_api_token": ("sin_variables_con_forma_de_secreto", lambda r: r["hook"]["inspect"]["signer"]["env_names"].append("API_TOKEN")),
    "no_new_privs_cero": ("no_root_y_sin_capacidades", lambda r: r["hook"]["isolation"].update(no_new_privs="0")),
}


def run_interactive(answer, out_dir):
    """E10b: el firmante en primer plano con aprobacion por terminal (stdin enlazado) y la URI solo en su salida."""
    import threading
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "evidence.jsonl").unlink(missing_ok=True)
    env = {**os.environ, "PROXY_ALLOW": "relay-lab:7777", "RELAY_URL": "ws://relay-lab:7777", "SN_ORIGIN": "https://sn.lab.invalid",
           "EVIDENCE_DIR": str(out_dir), "MODE": "sign", "APPROVAL_MODE": "tty", "APPROVAL_SCRIPT": "", "URI_FILE": "", "APPROVAL_TIMEOUT_S": "60"}
    run = {"answer": answer, "errors": [], "stdout": [], "client": None, "proxy": [], "relay": [], "evidence": [], "docker": {}}
    proc = None
    try:
        reh("down", "-v", "--remove-orphans", env=env, timeout=120)
        if reh("up", "-d", "relay-lab", "proxy", env=env, timeout=300).returncode:
            run["blocked"] = True
            return run
        proc = subprocess.Popen(REH + ["run", "--rm", "-T", "signer"], env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1)

        def reader():
            for line in proc.stdout:
                run["stdout"].append(line.rstrip("\n"))
        threading.Thread(target=reader, daemon=True).start()
        uri = None
        for _ in range(100):
            uri = next((l.split("URI 1: ", 1)[1].strip() for l in run["stdout"] if l.startswith("URI 1: bunker://")), None)
            if uri:
                break
            time.sleep(0.4)
        if not uri:
            run["errors"].append("el firmante no mostro la URI en 40 s: " + " | ".join(run["stdout"][-3:]))
            run["blocked"] = True
            return run
        run["_secret"] = re.search(r"secret=([A-Za-z0-9_-]+)", uri).group(1)
        cl = subprocess.Popen(REH + ["run", "--rm", "-T", "relay-lab", "python", "-m", "tests.interactive_client", uri], env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        for _ in range(100):                       # espera la pregunta y responde por la entrada estandar
            if any("Activar esta conexion?" in l for l in run["stdout"]):
                time.sleep(0.5)
                proc.stdin.write(answer + "\n")
                proc.stdin.flush()
                break
            time.sleep(0.4)
        try:
            cout, cerr = cl.communicate(timeout=90)
        except subprocess.TimeoutExpired:
            cl.kill()
            cout, cerr = cl.communicate()
        run["client"] = json.loads(cout.strip().splitlines()[-1]) if cout.strip().startswith("{") else {"error": (cout + cerr)[-200:]}
        cid = sh(["docker", "ps", "-q", "--filter", "name=nip46-rehearsal-signer-run"]).stdout.split()
        if cid:
            c = cid[0]
            insp = json.loads(sh(["docker", "inspect", c]).stdout)[0]
            lg = sh(["docker", "logs", c])
            ls = sh(["docker", "exec", c, "python", "-c", "import os,json;print(json.dumps([sorted(os.listdir('/tmp')),sorted(os.listdir('/ctl'))]))"])
            run["docker"] = {"log_driver": insp["HostConfig"]["LogConfig"]["Type"], "docker_logs": lg.stdout + lg.stderr,
                             "tmp_ctl": json.loads(ls.stdout.strip().splitlines()[-1]) if ls.returncode == 0 else None}
            sh(["docker", "kill", c])
        run["evidence"] = jsonl(out_dir / "evidence.jsonl")
        run["proxy"] = parse(reh("logs", "--no-color", "--no-log-prefix", "proxy", env=env).stdout)
        run["relay"] = parse(reh("logs", "--no-color", "--no-log-prefix", "relay-lab", env=env).stdout)
    except subprocess.TimeoutExpired as exc:
        run["errors"].append(f"timeout del orquestador: {exc}")
    finally:
        if proc and proc.poll() is None:
            proc.kill()
        reh("down", "-v", "--remove-orphans", env=env, timeout=120)
    return run


def eval_interactive(run):
    out = "\n".join(run["stdout"])
    secret = run.get("_secret", "")
    dec = [(d["approved"], d["reason"]) for d in ev_of(run, "decision") if d["kind"] == "connect"]
    ss = first(run["evidence"], "session_start")
    dk = run["docker"]
    others = json.dumps(run["evidence"]) + json.dumps(run["proxy"]) + json.dumps(run["relay"])
    yes = run["answer"] == "s"
    cl = run["client"] or {}
    obs = {"uri_lines_in_stdout": sum(1 for l in run["stdout"] if "bunker://" in l), "prompt_after_uri": None, "client": cl,
           "decisions": dec, "approval_mode": ss and ss["approval_mode"], "log_driver": dk.get("log_driver"),
           "docker_logs_len": len(dk.get("docker_logs", "")), "tmp_ctl": dk.get("tmp_ctl")}
    if not cl or "error" in cl and "connect" not in cl or not dk:
        return "INCONCLUSIVE", obs, "el cliente o la inspeccion del contenedor no se ejecutaron"
    idx_uri = next((i for i, l in enumerate(run["stdout"]) if "bunker://" in l), None)
    idx_q = next((i for i, l in enumerate(run["stdout"]) if "Activar esta conexion?" in l), None)
    obs["prompt_after_uri"] = idx_uri is not None and idx_q is not None and idx_q > idx_uri
    shown = next((l for l in run["stdout"] if l.startswith("Identidad desechable")), "")
    m = re.search(r"\): ([0-9a-f]{8})\.\.\.", shown)
    ident8 = m.group(1) if m else None
    checks = {
        "uri_una_sola_vez_y_pregunta_despues": obs["uri_lines_in_stdout"] == 1 and obs["prompt_after_uri"],
        "respuesta_del_cliente": (cl.get("connect") == "ack" and isinstance(cl.get("get_public_key"), str) and cl["get_public_key"][:8] == ident8) if yes
                                 else (cl.get("connect") == "unauthorized" and cl.get("get_public_key") == "unauthorized"),
        "evidencia_tty_y_decision": obs["approval_mode"] == "tty" and dec == [(yes, "humano")],
        "docker_no_conserva_salida": dk.get("log_driver") == "none" and secret not in dk.get("docker_logs", "") and "bunker://" not in dk.get("docker_logs", ""),
        "uri_no_escrita_en_archivos": dk.get("tmp_ctl") == [[], []],
        "secreto_ausente_de_evidencia_proxy_relay": len(secret) >= 20 and secret not in others and "bunker://" not in others,
    }
    obs["checks"] = checks
    return ("PASS" if all(checks.values()) else "FAIL"), obs, None if all(checks.values()) else [k for k, v in checks.items() if not v]


def run_rehearsal():
    ts =datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = RESULTS / f"rehearsal-{ts}"
    results = []

    def record(eid, objective, expected, run, verdict, obs, attribution, config):
        print(f"   {verdict}", flush=True)
        for k in ("client", "evidence", "proxy", "relay"):
            (base / f"{eid}.{k}.jsonl").parent.mkdir(parents=True, exist_ok=True)
            (base / f"{eid}.{k}.jsonl").write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in run[k]) + "\n", encoding="utf-8")
        if isinstance(obs, dict):
            obs = {k: v for k, v in obs.items() if k != "_secret"}
        results.append({"id": eid, "objective": objective, "config": config, "expected": expected, "observed": obs,
                        "errors": run["errors"], "verdict": "BLOCKED" if run.get("blocked") else verdict, "attribution": attribution})

    print("-> E8 politica restrictiva (NDK real -> firmante real minimo) ...", flush=True)
    run = reh_session("e8", "connect=y,sign=y", base / "E8")
    v, o, a = eval_e8(run) if not run.get("blocked") else ("BLOCKED", {}, "entorno")
    record("E8", "Politica kind 27235: 9 variantes invalidas se rechazan sin preguntar; la valida se firma; la repeticion del reto se rechaza",
           "9 rechazos con su comprobacion, 1 firma valida tras 1 aprobacion, replay rechazado", run, v, o, a, {"script": "connect=y,sign=y"})
    print("-> E8-control negativo del evaluador ...", flush=True)
    if v == "PASS":
        doctored = {**run, "client": [({**x, "signed": True} if x.get("ev") == "variant" and x["label"] == "wrong_origin" else x) for x in run["client"]]}
        cv, _, _ = eval_e8(doctored)
        results.append({"id": "E8-control", "objective": "El evaluador de E8 debe dar FAIL si una variante invalida llega a firmarse",
                        "config": {"metodo": "copia del crudo de E8 con wrong_origin.signed=true"}, "expected": "FAIL", "observed": {"verdict_del_evaluador": cv},
                        "errors": [], "verdict": "PASS" if cv == "FAIL" else "FAIL", "attribution": None if cv == "FAIL" else "el evaluador no detecta una firma indebida"})
        print(f"   {results[-1]['verdict']}", flush=True)
    print("-> E9 aprobacion humana: denegar, expirar, aprobar x2, tope ...", flush=True)
    run = reh_session("e9", "connect=y,sign=n,sign=timeout,sign=y,sign=y", base / "E9", timeout_s=3)
    v, o, a = eval_e9(run) if not run.get("blocked") else ("BLOCKED", {}, "entorno")
    record("E9", "Cada firma exige aprobacion humana; denegar o no responder no firma; tope de 2 firmas por sesion",
           "decisiones (n, timeout, s, s, tope); firman solo la 3.a y la 4.a", run, v, o, a, {"script": "connect=y,sign=n,sign=timeout,sign=y,sign=y", "timeout_s": 3, "max_signatures": 2})
    print("-> E9c denegacion por defecto de connect (guion vacio) ...", flush=True)
    run = reh_session("e9", "", base / "E9c", timeout_s=3, client_timeout=120, extra={"TIMEOUT_MS": "8000"})
    v, o, a = eval_e9c(run) if not run.get("blocked") else ("BLOCKED", {}, "entorno")
    record("E9c", "Sin aprobacion humana la conexion no se activa (denegar por defecto) y no se firma nada",
           "blockUntilReady no resuelve con exito; 0 eventos de politica y 0 firmas", run, v, o, a, {"script": "(vacio)"})
    print("-> E10 ciclo completo + proxy + red interna + aislamiento + sonda + interruptor ...", flush=True)
    out10 = base / "E10"
    run = reh_session("e2", "connect=y,sign=y", out10, hook=e10_hook)
    v, o, a = eval_e10(run, out10) if not run.get("blocked") else ("BLOCKED", {}, "entorno")
    record("E10", "Ciclo completo por la topologia real (firmante en red interna, proxy con lista blanca, relay local) y comprobaciones de seguridad",
           "firma valida; solo trafico por el proxy; aislamiento; logging none; sin secretos en la evidencia", run, v, o, a, {"script": "connect=y,sign=y"})
    print("-> E10-control negativos del evaluador de E10 ...", flush=True)
    import copy
    if v == "PASS":
        for name, (expected_check, mutate) in E10_CONTROLS.items():
            doctored = copy.deepcopy(run)
            mutate(doctored)
            cv, _, why = eval_e10(doctored, out10)
            good = cv == "FAIL" and why == [expected_check]
            results.append({"id": f"E10-control:{name}", "objective": "El evaluador de E10 debe fallar por la comprobacion esperada al alterar un dato",
                            "config": {"comprobacion_esperada": expected_check}, "expected": "FAIL solo por esa comprobacion",
                            "observed": {"verdict_del_evaluador": cv, "comprobaciones_fallidas": why}, "errors": [],
                            "verdict": "PASS" if good else "FAIL", "attribution": None if good else "el control no detecta lo esperado"})
            print(f"   {name}: {results[-1]['verdict']}", flush=True)
    for answer in ("s", "n"):
        print(f"-> E10b flujo interactivo (respuesta {answer}) ...", flush=True)
        outb = base / f"E10b-{answer}"
        irun = run_interactive(answer, outb)
        iv, io_, ia = eval_interactive(irun) if not irun.get("blocked") else ("BLOCKED", {}, "entorno: " + "; ".join(irun["errors"]))
        # el crudo del firmante solo se guarda tras comprobar que no contiene el secreto (la URI se redacta siempre)
        redacted = [re.sub(r"bunker://\S+", "bunker://[REDACTADO]", l) for l in irun["stdout"]]
        (base / f"E10b-{answer}.signer_stdout_redactado.txt").write_text("\n".join(redacted) + "\n", encoding="utf-8")
        for k in ("proxy", "relay", "evidence"):
            (base / f"E10b-{answer}.{k}.jsonl").write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in irun[k]) + "\n", encoding="utf-8")
        results.append({"id": f"E10b-{answer}", "objective": "Flujo interactivo: URI solo en la salida del firmante, aprobacion por terminal, sin exposicion en logs ni archivos",
                        "config": {"aprobacion": "tty (stdin enlazado, sin pseudo-TTY)", "respuesta": answer}, "expected": "ver definitions-real.md E10b",
                        "observed": io_, "errors": irun["errors"], "verdict": iv, "attribution": ia})
        print(f"   {iv}", flush=True)
        if iv == "PASS" and answer == "s":
            leaked = copy.deepcopy(irun)
            leaked["docker"]["docker_logs"] = "x " + irun["_secret"]
            cv, _, _ = eval_interactive(leaked)
            results.append({"id": "E10b-control", "objective": "El evaluador de E10b debe dar FAIL si el secreto aparece en docker logs",
                            "config": {}, "expected": "FAIL", "observed": {"verdict_del_evaluador": cv}, "errors": [],
                            "verdict": "PASS" if cv == "FAIL" else "FAIL", "attribution": None if cv == "FAIL" else "no detecta fuga en docker logs"})
            print(f"   control: {results[-1]['verdict']}", flush=True)
    print("-> E11 Compuerta B: modo observacion con aprobador que dice si a todo (NDK real, 11 solicitudes) ...", flush=True)
    run = reh_session("e8", "connect=y," + "sign=y," * 30, base / "E11", extra={"MODE": "observe"})
    v, o, a = eval_e11(run) if not run.get("blocked") else ("BLOCKED", {}, "entorno")
    record("E11", "Modo observacion (Compuerta B): ninguna solicitud de firma se firma ni se pregunta, aunque el aprobador diga si; se registra la estructura recibida",
           "11 solicitudes sin firma; 11 decisiones modo_observacion; estructura observada = la enviada; sin secretos", run, v, o, a,
           {"script": "connect=y + 30 x sign=y", "mode": "observe"})
    if v == "PASS":
        for name, (expected_check, mutate) in E11_CONTROLS.items():
            doctored = copy.deepcopy(run)
            mutate(doctored)
            cv, _, why = eval_e11(doctored)
            good = cv == "FAIL" and why == [expected_check]
            results.append({"id": f"E11-control:{name}", "objective": "El evaluador de E11 debe fallar solo por la comprobacion esperada al alterar un dato",
                            "config": {"comprobacion_esperada": expected_check}, "expected": "FAIL solo por esa comprobacion",
                            "observed": {"verdict_del_evaluador": cv, "comprobaciones_fallidas": why}, "errors": [],
                            "verdict": "PASS" if good else "FAIL", "attribution": None if good else "el control no detecta lo esperado"})
            print(f"   {name}: {results[-1]['verdict']}", flush=True)
    out = {"started_utc": ts, "results": results}
    (base / "results.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\n=== RESUMEN (ensayo local E8-E10) ===")
    for r in results:
        print(f"{r['verdict']:13} {r['id']:12} {r.get('attribution') or ''}")
    print("\nresultados crudos (excluidos de Git):", base)
    return 0 if all(r["verdict"] == "PASS" for r in results) else 1


# ------------------------------------------------------------------ plan de experimentos
def plan(signer):
    tag = "ref" if signer == "ref" else "py"
    sg = "firmante de referencia (Node, nostr-tools)" if signer == "ref" else "simulador Python (nip44/nip04 propios)"
    def cfg(reply, fault="none", extra=None):
        return {"signer": sg, "reply_mode": reply, "fault": fault, **(extra or {})}
    items = [
        ("E1", "e1", dict(id=f"E1-{tag}", kind="e1", objective="El firmante responde NIP-44 al connect NIP-04 de un NDKNip46Signer real (relay local)",
                          config=cfg("nip44"), expected="blockUntilReady() resuelve con la clave de identidad; connect NIP-04 y respuesta NIP-44 observados en el relay; NDK pasa de nip04 a nip44"),
         dict(signer=signer, reply_mode="nip44", scenario="e1")),
        ("E4", "e4", dict(id=f"E4-{tag}", kind="e4", objective="Modo respuesta NIP-04 a todo",
                          config=cfg("nip04"), expected="flujo completo (connect, get_public_key, sign_event 27235) con TODOS los eventos NIP-04; NDK nunca cambia de esquema; firma valida"),
         dict(signer=signer, reply_mode="nip04", scenario="e4")),
        ("E4m", "e4", dict(id=f"E4m-{tag}", kind="e4", objective="COMPLEMENTO: modo espejo (misma salida esperada que E4 frente a NDK)",
                           config=cfg("mirror"), expected="igual que E4"),
         dict(signer=signer, reply_mode="mirror", scenario="e4")),
        ("E2", "e2", dict(id=f"E2-{tag}", kind="e2", objective="Tras E1, esquema de las solicitudes siguientes y sign_event kind 27235 con la forma exacta de Stacker News",
                          config=cfg("nip44"), expected="get_public_key y sign_event llegan en NIP-44; la firma verifica sin conexion sobre el id calculado por NDK; pasa las comprobaciones de servidor de SN"),
         dict(signer=signer, reply_mode="nip44", scenario="e2")),
        ("E6", "e6", dict(id=f"E6-{tag}", kind="e6", objective="Orden y carrera: respuestas consecutivas rapidas (operacionalizacion: ack, clave publica y 20 sign_event concurrentes sin retardo)",
                          config=cfg("nip44", extra={"jitter_ms": 0, "n_sign": 20}), expected="sin oscilaciones de esquema (maximo una transicion nip04->nip44) ni bloqueos; 20/20 firmas validas"),
         dict(signer=signer, reply_mode="nip44", scenario="e6", n_sign=20)),
        ("E6j", "e6", dict(id=f"E6j-{tag}", kind="e6", objective="Variante de E6 con retardo aleatorio (0-40 ms) que reordena respuestas",
                           config=cfg("nip44", extra={"jitter_ms": 40, "n_sign": 20}), expected="igual que E6"),
         dict(signer=signer, reply_mode="nip44", scenario="e6", n_sign=20, jitter_ms=40)),
    ]
    expect7 = {
        "wrong_id": "respuesta con id ajeno no resuelve; resuelve solo al llegar la correcta (>= 1,4 s)",
        "error_field": "blockUntilReady rechaza con el texto del campo error ('lab-denied')",
        "malformed_json": "texto plano no JSON: NDK lo descarta (error de parseo registrado) y resuelve con la respuesta correcta posterior",
        "garbage": "cifrado indescifrable: NDK lo descarta tras intentar ambos esquemas y resuelve con la correcta posterior",
        "bad_mac": "MAC NIP-44 invalido: error 'invalid MAC' en NDK y resuelve con la correcta posterior",
        "spoof": "PREDICCION del analisis estatico: NDK acepta un ack firmado por otra clave si el id coincide (correlacion solo por id)",
        "duplicate": "respuesta duplicada con el mismo id: se procesa dos veces pero resuelve una sola vez, sin errores",
        "unknown_id_first": "respuesta con id desconocido se ignora; resuelve con la correcta",
        "auth_url": "NDK emite authUrl con la URL y resuelve cuando llega la respuesta final con el mismo id (>= 0,9 s)",
        "get_pubkey_error": "PREDICCION: get_public_key con error resuelve con clave indefinida, sin rechazar (N7)",
        "mixed": "esquemas mezclados: NDK oscila entre esquemas (>= 2 transiciones) y aun asi resuelve",
    }
    for fault in E7_FAULTS:
        items.append((f"E7:{fault}", "e7", dict(id=f"E7-{fault}-{tag}", kind="e7", fault=fault, objective=f"E7 (errores/correlacion): {fault}",
                                               config=cfg("nip44", fault), expected=expect7[fault]),
                      dict(signer=signer, reply_mode="nip44", fault=fault, scenario="e7", timeout_ms=6000)))
    return items


def run_plan(signer, only=None):
    out = []
    for key, _kind, exp, spec in plan(signer):
        if only and key not in only and exp["id"] not in only:
            continue
        spec = dict(spec)
        exp = dict(exp)
        print(f"-> {exp['id']} ...", flush=True)
        run = run_scenario(spec)
        res = evaluate(exp, run)
        res["raw"] = {"client": run["client"], "signer": run["signer"], "relay": run["relay"]}
        out.append(res)
        print(f"   {res['verdict']}  ({res.get('duration_s')} s)", flush=True)
    return out


def decision(results):
    v = {r["id"]: r["verdict"] for r in results}
    e1, e2, e4 = v.get("E1-py"), v.get("E2-py"), v.get("E4-py")
    if e1 == "PASS" and e2 == "PASS":
        return "NIP-44 como respuesta predeterminada (E1 y E2 con Python: PASS)"
    if "INCONCLUSIVE" in (e1, e2, e4) or "BLOCKED" in (e1, e2, e4) or None in (e1, e2, e4):
        return "SIN DECISION: pruebas con Python inconclusas o bloqueadas (no se declara incompatibilidad)"
    if (e1 == "FAIL" or e2 == "FAIL") and e4 == "PASS":
        return "modo espejo NIP-04 provisional (E1/E2 fallan y E4 pasa)"
    return "BLOQUEO de interoperabilidad (E1/E2 y E4 fallan con Python)"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", choices=["all", "units", "isolation", "ref", "e5", "py", "rehearsal"], default="all")
    ap.add_argument("--only", nargs="*", help="ids concretos (p. ej. E1 E7:spoof)")
    args = ap.parse_args()
    if args.stage == "rehearsal":   # Fase 1.0A.2: no forma parte de `all` (que reproduce la Fase 1.0A.1)
        return run_rehearsal()
    started = datetime.datetime.now(datetime.timezone.utc)
    results = []
    if args.stage in ("all", "units"):
        print("-> E0 pruebas propias ...", flush=True)
        results.append(run_units())
    if args.stage in ("all", "isolation"):
        print("-> verificacion de aislamiento ...", flush=True)
        results.append(verify_isolation())
    if args.stage in ("all", "ref"):
        results += run_plan("ref", args.only)
    if args.stage in ("all", "py", "e5"):
        pass
    if args.stage in ("all", "py"):
        # E3 (simulador Python): se ejecuta aqui para respetar el orden aprobado: referencia -> E3 -> E5 -> repeticion Python
        print("-> E3-py ...", flush=True)
        exp = dict(id="E3-py", kind="e3", objective="Descifrar en Python el primer connect NIP-04 real de NDK",
                   config={"signer": "simulador Python", "reply_mode": "nip44"},
                   expected="texto plano identico al que cifro NDK (SHA-256 igual); sin errores de relleno")
        run = run_scenario(dict(signer="py", reply_mode="nip44", scenario="e3"))
        res = evaluate(exp, run)
        res["raw"] = {"client": run["client"], "signer": run["signer"], "relay": run["relay"]}
        results.append(res)
        print(f"   {res['verdict']}", flush=True)
    if args.stage in ("all", "e5"):
        print("-> E5/E5b cruzadas ...", flush=True)
        results += run_e5()
    if args.stage in ("all", "py"):
        results += run_plan("py", args.only)
    info = environment_info() if args.stage == "all" else None
    out_dir = RESULTS / ("run-" + started.strftime("%Y%m%dT%H%M%SZ"))
    out_dir.mkdir(parents=True, exist_ok=True)
    for r in results:  # el crudo va a ficheros aparte
        raw = r.pop("raw", None)
        if raw:
            for actor, lines in raw.items():
                (out_dir / f"{r['id']}.{actor}.jsonl").write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in lines) + "\n", encoding="utf-8")
    summary = {"started_utc": started.isoformat(timespec="seconds"), "environment": info, "results": results,
               "decision_rule_python_runs": decision(results) if args.stage == "all" else None}
    (out_dir / "results.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\n=== RESUMEN ===")
    for r in results:
        print(f"{r['verdict']:13} {r['id']:26} {r.get('attribution') or ''}")
    if summary["decision_rule_python_runs"]:
        print("\nREGLA DE DECISION:", summary["decision_rule_python_runs"])
    print("\nresultados crudos (excluidos de Git):", out_dir)
    return 0 if all(r["verdict"] in ("PASS",) for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
