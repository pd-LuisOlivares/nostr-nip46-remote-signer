"""Verificación obligatoria del usuario `evaluador` en la SQLite de la instalación oficial, sobre recursos NUEVOS y aislados (nunca B6.2).
No imprime contraseñas, hashes completos ni tokens. Usa SOLO recursos propios y nuevos (proyectos nip46-evalcheck, nip46-evalcheck2 y nip46-evaluacion-2, puertos 18095 a 18097, imagen :evalcheck); si alguno existe, no hace nada. Al final los elimina (verificados por etiqueta de proyecto). Necesita Docker.
Uso (desde cualquier directorio): python -I -X utf8 tools/validate_official_install.py <raiz-del-repositorio> <evidencia.json>"""
import hashlib
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
repo, evidence_path = Path(sys.argv[1]), Path(sys.argv[2])
IMAGE = "nostr-nip46-remote-signer:evalcheck"
P1, P2, P3 = "nip46-evalcheck", "nip46-evalcheck2", "nip46-evaluacion-2"  # P3 = el nombre que documenta el README para «otro volumen»
PORT = {P1: "18095", P2: "18096", P3: "18097"}
B62 = "nostr-nip46-remote-signer-app-1"
results: dict[str, object] = {}
checks: list[tuple[str, bool]] = []


def check(name: str, ok: bool, detail: object = "") -> None:
    checks.append((name, ok))
    print(("PASS " if ok else "FAIL ") + name + (f" -> {detail}" if detail != "" else ""))


def run(*args: str, env_extra: dict[str, str] | None = None, cwd: Path | None = None, timeout: int = 900) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("ADMIN_") and k not in ("APP_PORT", "APP_IMAGE", "COMPOSE_PROJECT_NAME")}
    env.update(env_extra or {})
    return subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)


def compose(project: str, *args: str, extra: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return run("docker", "compose", "--env-file", "deploy/demo.env", "-p", project, *args, env_extra={"APP_PORT": PORT[project], "APP_IMAGE": IMAGE, **(extra or {})}, cwd=repo)


def inspect(name: str) -> dict:
    out = run("docker", "inspect", name).stdout
    return json.loads(out)[0] if out.strip().startswith("[") else {}


def wait_healthy(project: str) -> bool:
    for _ in range(90):
        if run("docker", "inspect", f"{project}-app-1", "--format", "{{.State.Health.Status}}").stdout.strip() == "healthy":
            return True
        time.sleep(2)
    return False


def http(project: str, path: str, body: dict | None = None) -> int:
    base = f"http://127.0.0.1:{PORT[project]}"
    req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None, method="POST" if body is not None else "GET",
                                 headers={"Origin": base, **({"Content-Type": "application/json"} if body is not None else {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return int(r.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)


def login(project: str, user: str, password: str) -> int:
    return http(project, "/api/auth/login", {"username": user, "password": password})


QUERY = ("import sqlite3,json,hashlib,os;p='/data/nip46.db';c=sqlite3.connect('file:'+p+'?mode=ro',uri=True);"
         "r=c.execute('select id,username,is_active,password_hash,created_at,updated_at,last_login_at from admins').fetchall();"
         "print(json.dumps({'file':p,'mode':oct(os.stat(p).st_mode&0o777),'count':len(r),'rows':[{'id':x[0],'username':x[1],'active':x[2],'argon2id':x[3].startswith('$argon2id$'),"
         "'params':x[3].split('$')[3] if x[3].count('$')>=4 else '?','hash_len':len(x[3]),'hash_sha8':hashlib.sha256(x[3].encode()).hexdigest()[:8],'created':x[4],'updated':x[5]} for x in r]}))")


def db(project: str) -> dict:
    out = run("docker", "exec", f"{project}-app-1", "python", "-c", QUERY).stdout.strip()
    return json.loads(out)


def stable(d: dict) -> list:
    return [(r["id"], r["username"], r["active"], r["hash_sha8"], r["created"], r["updated"]) for r in d["rows"]]


def b62_state() -> dict:
    i = inspect(B62)
    return {"id": i.get("Id", "")[:12], "started": i.get("State", {}).get("StartedAt"), "restarts": i.get("RestartCount"), "health": i.get("State", {}).get("Health", {}).get("Status")}


def port_free(port: str) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", int(port))) != 0


# ------------------------------------------------------------------------------------------------ credenciales DESDE el README
readme = (repo / "README.md").read_text(encoding="utf-8")
m = re.search(r"\|\s*`(evaluador)`\s*\|\s*`([^`]+)`\s*\|", readme)
assert m, "no se encontró la tabla de credenciales del README"
USER, PW = m.group(1), m.group(2)
demo = {k.strip(): v.strip() for k, _, v in (l.partition("=") for l in (repo / "deploy" / "demo.env").read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#"))}
check("las credenciales del README coinciden con deploy/demo.env", demo["ADMIN_USERNAME"] == USER and demo["ADMIN_PASSWORD"] == PW)

# ------------------------------------------------------------------------------------------------ precondiciones y B6.2 (solo lectura)
b62_before = b62_state()
results["b62_antes"] = b62_before
for p in (P1, P2, P3):
    existing = run("docker", "ps", "-a", "-q", "--filter", f"label=com.docker.compose.project={p}").stdout.split() + run("docker", "volume", "ls", "-q", "--filter", f"label=com.docker.compose.project={p}").stdout.split()
    check(f"recursos del proyecto {p} NO existían antes", not existing and port_free(PORT[p]), f"puerto {PORT[p]} libre")
if not all(ok for _, ok in checks):
    sys.exit("precondiciones incumplidas: no se hace nada (la limpieza solo se permite sobre recursos creados por esta prueba)")

try:
    # -------------------------------------------------------------------------------------------- 1. instalación nueva, construcción sin caché
    b = compose(P1, "build", "--no-cache")
    check("construcción Docker sin caché", b.returncode == 0, "" if b.returncode == 0 else b.stderr[-300:])
    u = compose(P1, "up", "-d")
    check("arranque del perfil oficial en un puerto alternativo", u.returncode == 0 and wait_healthy(P1), f"proyecto {P1}, puerto {PORT[P1]}")
    cid1 = inspect(f"{P1}-app-1").get("Id", "")
    mounts = [(x["Name"], x["Destination"]) for x in inspect(f"{P1}-app-1")["Mounts"] if x["Type"] == "volume"]
    check("volumen persistente de la instalación (no el de B6.2)", mounts == [(f"{P1}_app_data", "/data")] and mounts[0][0] != "nostr-nip46-remote-signer_app_data", mounts)
    d0 = db(P1)
    r0 = d0["rows"][0] if d0["rows"] else {}
    check("SQLite /data/nip46.db con exactamente 1 administrador", d0["count"] == 1 and d0["file"] == "/data/nip46.db", {"modo": d0["mode"]})
    check("evaluador existe, está activo y su hash es Argon2id", r0.get("username") == "evaluador" and r0.get("active") == 1 and r0.get("argon2id") is True, {"id": r0.get("id"), "params": r0.get("params"), "longitud_hash": r0.get("hash_len")})
    check("el hash no contiene la contraseña", PW not in json.dumps(d0))
    logs = run("docker", "logs", f"{P1}-app-1")
    text = logs.stdout + logs.stderr
    check("registro: admin_bootstrap result=created y sin la contraseña", "admin_bootstrap result=created" in text and PW not in text)
    # -------------------------------------------------------------------------------------------- 2. login real
    check("login correcto con las credenciales del README → HTTP 200", login(P1, USER, PW) == 200)
    check("contraseña incorrecta → HTTP 401", login(P1, USER, PW + "x") == 401)
    check("usuario inexistente → HTTP 401", login(P1, "admin", PW) == 401)
    # -------------------------------------------------------------------------------------------- 3. reinicio del contenedor aislado
    rs = run("docker", "restart", f"{P1}-app-1")
    check("reinicio del contenedor aislado", rs.returncode == 0 and wait_healthy(P1))
    d1 = db(P1)
    check("tras el reinicio: mismo administrador (sin duplicar ni sobrescribir)", d1["count"] == 1 and stable(d1) == stable(d0), {"sha8": d1["rows"][0]["hash_sha8"]})
    check("tras el reinicio: login 200 con las credenciales del README", login(P1, USER, PW) == 200)
    check("tras el reinicio: contraseña incorrecta → 401", login(P1, USER, PW + "x") == 401)
    text = (lambda l: l.stdout + l.stderr)(run("docker", "logs", f"{P1}-app-1"))
    check("registro del reinicio: admin_bootstrap result=exists (no recreado)", "admin_bootstrap result=exists" in text)
    # -------------------------------------------------------------------------------------------- 4. idempotencia del despliegue
    u2 = compose(P1, "up", "-d")
    same = inspect(f"{P1}-app-1").get("Id", "") == cid1
    check("volver a ejecutar el mismo comando no recrea el contenedor ni cambia nada", u2.returncode == 0 and same and stable(db(P1)) == stable(d0))
    u3 = compose(P1, "up", "-d", "--force-recreate", extra={"ADMIN_PASSWORD": "otra-contrasena-distinta-1234"})  # contenedor nuevo y contraseña inicial DISTINTA en el entorno
    check("recrear el contenedor con otra contraseña inicial en el entorno", u3.returncode == 0 and wait_healthy(P1))
    d2 = db(P1)
    check("tras recrear: administrador intacto (misma fila, mismo hash, sin duplicar)", d2["count"] == 1 and stable(d2) == stable(d0))
    check("tras recrear: la contraseña del README sigue valiendo (200) y la del entorno NO (401)", login(P1, USER, PW) == 200 and login(P1, USER, "otra-contrasena-distinta-1234") == 401)
    d_ = compose(P1, "down")
    u4 = compose(P1, "up", "-d")
    check("down (sin -v) y up: la base persiste en el volumen", d_.returncode == 0 and u4.returncode == 0 and wait_healthy(P1) and stable(db(P1)) == stable(d0) and login(P1, USER, PW) == 200)
    results["instalacion_nueva"] = {"volumen": mounts[0][0], "base": d0["file"], "modo_archivo": d0["mode"], "usuario": r0.get("username"), "activo": r0.get("active"), "argon2id": r0.get("argon2id"),
                                    "parametros": r0.get("params"), "longitud_hash": r0.get("hash_len"), "hash_sha256_8": r0.get("hash_sha8"), "administradores": d0["count"]}

    # -------------------------------------------------------------------------------------------- 5. base existente con OTRO administrador y sin evaluador
    toy_user, toy_pw = "otroadmin", "toy-" + secrets.token_hex(10)
    compose(P2, "up", "-d", extra={"ADMIN_USERNAME": toy_user, "ADMIN_PASSWORD": toy_pw})
    check("proyecto 2: base creada con otro administrador", wait_healthy(P2) and login(P2, toy_user, toy_pw) == 200)
    other0 = db(P2)
    compose(P2, "down")
    u5 = compose(P2, "up", "-d")  # ahora con el perfil oficial: ADMIN_USERNAME=evaluador y la contraseña del README
    check("proyecto 2: arranca con el perfil oficial sobre esa base", u5.returncode == 0 and wait_healthy(P2))
    other1 = db(P2)
    check("la base con otro administrador NO se modifica ni se le añade evaluador", other1["count"] == 1 and stable(other1) == stable(other0) and other1["rows"][0]["username"] == toy_user)
    check("evaluador NO se crea automáticamente en esa base (login → 401)", login(P2, USER, PW) == 401)
    check("el administrador preexistente sigue pudiendo entrar (200)", login(P2, toy_user, toy_pw) == 200)
    text2 = (lambda l: l.stdout + l.stderr)(run("docker", "logs", f"{P2}-app-1"))
    check("registro: result=exists, sin errores ni contraseñas", "admin_bootstrap result=exists" in text2 and PW not in text2 and toy_pw not in text2)
    results["otro_administrador_preexistente"] = {"administradores": other1["count"], "usuario_preexistente_intacto": stable(other1) == stable(other0), "evaluador_creado": False}
    # procedimiento documentado: proyecto y volumen NUEVOS (nombre exacto del README), la base anterior intacta
    u6 = compose(P3, "up", "--build", "-d")
    check("procedimiento del README (-p nip46-evaluacion-2, otro puerto): evaluador se crea y entra (200)", u6.returncode == 0 and wait_healthy(P3) and login(P3, USER, PW) == 200)
    d3 = db(P3)
    v3 = [(x["Name"]) for x in inspect(f"{P3}-app-1")["Mounts"] if x["Type"] == "volume"]
    check("... con volumen propio y la base anterior sigue intacta", v3 == [f"{P3}_app_data"] and d3["rows"][0]["username"] == "evaluador" and stable(db(P2)) == stable(other0))
    results["procedimiento_volumen_nuevo"] = {"proyecto": P3, "volumen": v3[0], "evaluador_200": True}
finally:
    # ---------------------------------------------------------------------------------------- limpieza SOLO de los recursos propios (verificados por etiqueta de proyecto)
    for p in (P1, P2, P3):
        owned = run("docker", "ps", "-a", "-q", "--filter", f"label=com.docker.compose.project={p}").stdout.split()
        vols = run("docker", "volume", "ls", "-q", "--filter", f"label=com.docker.compose.project={p}").stdout.split()
        assert all(v.startswith(p + "_") for v in vols), vols
        compose(p, "down", "-v")
        left = run("docker", "ps", "-a", "-q", "--filter", f"label=com.docker.compose.project={p}").stdout.split() + run("docker", "volume", "ls", "-q", "--filter", f"label=com.docker.compose.project={p}").stdout.split()
        check(f"limpieza del proyecto {p} (contenedores/volúmenes propios eliminados)", not left, f"{len(owned)} contenedor(es), {len(vols)} volumen(es)")
    run("docker", "image", "rm", IMAGE)
    b62_after = b62_state()
    results["b62_despues"] = b62_after
    check("B6.2 intacto (mismo contenedor, mismo arranque, 0 reinicios, sano)", b62_after == b62_before, b62_after)

results["comprobaciones"] = [{"nombre": n, "ok": ok} for n, ok in checks]
results["total"], results["fallidas"] = len(checks), sum(1 for _, ok in checks if not ok)
evidence_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\nTOTAL {len(checks)} comprobaciones, {results['fallidas']} fallidas")
sys.exit(1 if results["fallidas"] else 0)
