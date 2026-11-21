#!/usr/bin/env python3
"""Regresión B2: el firmante DEL PRODUCTO frente al cliente NDK 2.12.2 real (escenarios E1, E2, E3 y E8 del laboratorio).

Se ejecuta en el HOST (solo biblioteca estándar). Todo ocurre en una red Docker `internal` (sin Internet, sin puertos publicados): NO toca
relays públicos ni Stacker News. Los criterios están fijados aquí, antes de ejecutar. Resultados en lab/results/product-regression-<fecha>/
(excluido de Git). Veredicto: PASS solo si todos los criterios de todos los escenarios se cumplen.

Uso:  python lab/run_product_regression.py          # servicio del producto (runner.py)
      python lab/run_product_regression.py --api    # aplicacion completa (Uvicorn + API HTTP), P-33
"""
import datetime
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

LAB = Path(__file__).resolve().parent
COMPOSE = ["docker", "compose", "-f", str(LAB / "product" / "compose.yaml"), "-p", "nip46-product"]
HEX64 = re.compile(r"[0-9a-f]{64}")


def sh(args: list[str], env: dict[str, str] | None = None, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)


def compose(*args: str, env: dict[str, str] | None = None, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    return sh([*COMPOSE, *args], env=env, timeout=timeout)


def parse(text: str) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def events(evs: list[dict[str, object]], name: str) -> list[dict[str, object]]:
    return [e for e in evs if e.get("ev") == name]


def credential_from_logs(env: dict[str, str]) -> str:
    """El codigo de acceso del operador solo existe en el registro del contenedor (se muestra una vez al arrancar)."""
    for _ in range(60):
        out = compose("logs", "--no-color", "--no-log-prefix", "app", env=env).stdout
        match = re.search(r"ESTA ejecucion[^:]*: ([A-Za-z0-9_-]{20,})", out)
        if match:
            return match.group(1)
        time.sleep(0.5)
    return ""


def run_api_scenario(scenario: str) -> dict[str, object]:
    """P-33: Uvicorn + FastAPI + runtime + firmante + relay + NDK real, operados por la API HTTP (driver.py)."""
    env = {**os.environ, "SCENARIO": scenario}
    run: dict[str, object] = {"scenario": scenario, "mode": "api", "errors": []}
    errors: list[str] = run["errors"]  # type: ignore[assignment]
    driver = None
    try:
        compose("down", "-v", "--remove-orphans", env=env, timeout=120)
        up = compose("up", "-d", "relay", "app", env=env, timeout=240)
        if up.returncode:
            errors.append("up fallo: " + up.stderr[-300:])
            return run
        credential = credential_from_logs(env)
        if not credential:
            errors.append("no se encontro la credencial de operador en el registro de la aplicacion")
            return run
        driver = subprocess.Popen([*COMPOSE, "exec", "-T", "-e", f"API_TOKEN={credential}", "app", "python", "/lab-product/driver.py"], env=env,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        time.sleep(0.2)
        cl = compose("run", "--rm", "-T", "client", env=env, timeout=180)
        run["client"] = parse(cl.stdout)
        if cl.returncode:
            errors.append(f"cliente salio con codigo {cl.returncode}: {cl.stderr[-200:]}")
        out, err = driver.communicate(timeout=150)
        run["signer"] = parse(out)
        if driver.returncode:
            errors.append(f"driver salio con codigo {driver.returncode}: {err[-200:]}")
        run["relay"] = compose("logs", "--no-color", "--no-log-prefix", "relay", env=env).stdout
        run["app_log"] = compose("logs", "--no-color", "--no-log-prefix", "app", env=env).stdout.replace(credential, "[REDACTADO:credencial]")
    except subprocess.TimeoutExpired as exc:
        errors.append(f"timeout del orquestador: {exc}")
        if driver:
            driver.kill()
    finally:
        compose("down", "-v", "--remove-orphans", env=env, timeout=120)
    return run


def run_scenario(scenario: str) -> dict[str, object]:
    env = {**os.environ, "SCENARIO": scenario}
    run: dict[str, object] = {"scenario": scenario, "errors": []}
    errors: list[str] = run["errors"]  # type: ignore[assignment]
    try:
        compose("down", "-v", "--remove-orphans", env=env, timeout=120)
        up = compose("up", "-d", "relay", "signer", env=env, timeout=240)
        if up.returncode:
            errors.append("up fallo: " + up.stderr[-300:])
            return run
        for _ in range(80):
            if events(parse(compose("logs", "--no-color", "--no-log-prefix", "signer", env=env).stdout), "ready"):
                break
            time.sleep(0.5)
        else:
            errors.append("el firmante del producto no llego a `ready`")
            run["signer_raw_tail"] = compose("logs", "--no-color", "--no-log-prefix", "signer", env=env).stdout[-600:]
            return run
        cl = compose("run", "--rm", "-T", "client", env=env, timeout=180)
        run["client"] = parse(cl.stdout)
        if cl.returncode:
            errors.append(f"cliente salio con codigo {cl.returncode}: {cl.stderr[-200:]}")
        compose("stop", "-t", "8", "signer", env=env, timeout=60)  # SIGTERM: el runner vuelca la auditoria y deja session_end
        run["signer"] = parse(compose("logs", "--no-color", "--no-log-prefix", "signer", env=env).stdout)
        run["relay"] = compose("logs", "--no-color", "--no-log-prefix", "relay", env=env).stdout
    except subprocess.TimeoutExpired as exc:
        errors.append(f"timeout del orquestador: {exc}")
    finally:
        compose("down", "-v", "--remove-orphans", env=env, timeout=120)
    return run


def check(name: str, ok: bool, detail: str = "") -> dict[str, object]:
    return {"criterio": name, "ok": bool(ok), "detalle": detail}


def final_of(run: dict[str, object]) -> dict[str, object]:
    finals = events(run.get("signer", []), "final")  # type: ignore[arg-type]
    return finals[-1] if finals else {}


def audit_events(run: dict[str, object]) -> list[str]:
    return [str(e.get("event")) for e in events(run.get("signer", []), "audit")]  # type: ignore[arg-type]


def evaluate(run: dict[str, object]) -> list[dict[str, object]]:
    scenario, client = str(run["scenario"]), run.get("client", [])
    ready = (events(client, "ready_result") or [{}])[0]  # type: ignore[arg-type]
    final, audit = final_of(run), audit_events(run)
    c = [check("sin errores del orquestador", not run["errors"], "; ".join(run["errors"]))]  # type: ignore[arg-type]
    c += [check("NDK completa connect + get_public_key y la identidad coincide", ready.get("ok") is True and ready.get("matches_identity") is True,
                f"error={ready.get('error')}"),
          check("el producto deja session_end con motivo y firmas", "session_end" in audit and "signatures" in final),
          check("cierre ordenado del producto (SIGTERM)", final.get("end_reason") in ("detenido_por_el_operador", "apagado_de_la_aplicacion"),
                f"end_reason={final.get('end_reason')}")]
    if scenario == "e1":
        c.append(check("E1: ninguna firma sin solicitarla", final.get("signatures") == 0))
    elif scenario in ("e2", "e3"):
        login = (events(client, "login_event") or [{}])[0]  # type: ignore[arg-type]
        c += [check("login firmado y verificado como lo haria el servidor (id, firma, reto, identidad)", login.get("all_ok") is True, str(login)[:160]),
              check("exactamente una firma", final.get("signatures") == 1),
              check("la aprobacion automatica solo recibio solicitudes con las 11 comprobaciones superadas",
                    all(e.get("checks_ok") for e in events(run.get("signer", []), "auto_approved")))]  # type: ignore[arg-type]
    elif scenario == "e8":
        variants = {str(v.get("label")): v for v in events(client, "variant")}  # type: ignore[arg-type]
        invalid = ["wrong_origin", "wrong_content", "wrong_method", "extra_tag", "wrong_kind", "stale", "future", "bad_challenge", "tag_order"]
        c += [check("las 9 variantes invalidas se rechazan", all(variants.get(n, {}).get("signed") is False for n in invalid),
                    str({n: variants.get(n, {}).get("signed") for n in invalid})),
              check("la variante valida se firma intacta y verificable",
                    all(variants.get("valid", {}).get(k) is True for k in ("signed", "id_ok", "sig_ok", "pubkey_is_identity", "tags_unchanged"))),
              check("la repeticion del reto firmado se rechaza", variants.get("replay_same_challenge", {}).get("signed") is False),
              check("una sola firma y una sola solicitud llego al operador (las invalidas no se le ofrecen)",
                    final.get("signatures") == 1 and len(events(run.get("signer", []), "auto_approved")) == 2,  # connect + la valida
                    f"aprobadas={len(events(run.get('signer', []), 'auto_approved'))}")]  # type: ignore[arg-type]
    blob = json.dumps(run.get("signer", [])) + str(run.get("relay", ""))
    c.append(check("sin secretos en la auditoria del producto (bunker://, secret=, nsec, hex de 64 en la auditoria)",
                   not re.search(r"bunker://|secret=|nsec1", blob) and not HEX64.search(json.dumps([e for e in run.get("signer", []) if e.get("ev") == "audit"]))))  # type: ignore[union-attr]
    return c


def main() -> int:
    api_mode = "--api" in sys.argv[1:]
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
    out = LAB / "results" / f"product-{'api' if api_mode else 'regression'}-{stamp}"
    out.mkdir(parents=True, exist_ok=True)
    summary, ok_all = [], True
    for scenario in ("e1", "e2", "e3", "e8"):
        run = run_api_scenario(scenario) if api_mode else run_scenario(scenario)
        criteria = evaluate(run)
        ok = all(c["ok"] for c in criteria)
        ok_all &= ok
        summary.append({"scenario": scenario, "verdict": "PASS" if ok else "FAIL", "criteria": criteria})
        (out / f"{scenario}.json").write_text(json.dumps({"run": run, "criteria": criteria}, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"{scenario}: {'PASS' if ok else 'FAIL'}", flush=True)
        for c in criteria:
            if not c["ok"]:
                print(f"   - FALLA: {c['criterio']} {c['detalle']}", flush=True)
    (out / "summary.json").write_text(json.dumps({"verdict": "PASS" if ok_all else "FAIL", "scenarios": summary}, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"veredicto: {'PASS' if ok_all else 'FAIL'}  ->  {out.relative_to(LAB.parent)}", flush=True)
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
