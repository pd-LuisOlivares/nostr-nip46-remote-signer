"""B6.1D: comprobaciones AUTOMATIZADAS de solo lectura contra la aplicación local de la demostración (Docker Compose, proyecto `nip46-manual`).

Lee la contraseña de PRUEBA de un archivo local (`--password-file`) sin imprimirla ni registrarla; muestra solo resultados verdadero/falso y datos no sensibles.
No crea identidades, no inicia el firmante, no toca las solicitudes y no se conecta a nada fuera de 127.0.0.1 y del propio Docker local.
Uso: python lab/manual/check_live.py --password-file <ruta> [--username admin-manual] [--port 8000] [--project nip46-manual] [--evidence resultado.json]
"""
import argparse
import base64
import json
import re
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RESULTS: list[dict[str, object]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append({"comprobacion": name, "resultado": "PASS" if ok else "FAIL", "detalle": detail})
    print(("PASS  " if ok else "FAIL  ") + name + (f"  [{detail}]" if detail else ""), flush=True)


def sh(*args: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(args), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)


def call(base: str, method: str, path: str, body: object | None = None, headers: dict[str, str] | None = None) -> tuple[int, dict[str, str], bytes]:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(base + path, data=data, method=method, headers={**({"Content-Type": "application/json"} if data else {}), **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, {k.lower(): v for k, v in resp.headers.items()}, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, {k.lower(): v for k, v in exc.headers.items()}, exc.read()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--password-file", required=True)
    ap.add_argument("--username", default="admin-manual")
    ap.add_argument("--port", default="8000")
    ap.add_argument("--project", default="nip46-manual")
    ap.add_argument("--evidence")
    a = ap.parse_args()
    password = Path(a.password_file).read_text(encoding="utf-8").strip()
    base = f"http://127.0.0.1:{a.port}"
    dc = ["docker", "compose", "-p", a.project]
    container = f"{a.project}-app-1"

    # --- contenedor
    info = json.loads(sh("docker", "inspect", container).stdout)[0]
    check("contenedor healthy", info["State"]["Health"]["Status"] == "healthy", info["State"]["Health"]["Status"])
    check("raíz de solo lectura, sin capacidades y usuario no root", info["HostConfig"]["ReadonlyRootfs"] is True and info["HostConfig"]["CapDrop"] == ["ALL"] and info["Config"]["User"] in ("app", "10001", "10001:10001"),
          f"user={info['Config']['User']}")
    ports = info["NetworkSettings"]["Ports"].get("8000/tcp") or []
    check("puerto publicado solo en 127.0.0.1", bool(ports) and all(p["HostIp"] == "127.0.0.1" for p in ports))
    env = {e.split("=", 1)[0]: e.split("=", 1)[1] for e in info["Config"]["Env"] if "=" in e}
    check("la contraseña inicial ya NO está en el entorno del contenedor", env.get("ADMIN_PASSWORD", "") == "")

    # --- SQLite
    probe = sh(*dc, "exec", "-T", "app", "python", "-c",
               "import json,os,sqlite3\n"
               "p='/data/nip46.db'\n"
               "c=sqlite3.connect(p)\n"
               "r=c.execute('select username,password_hash,is_active,last_login_at from admins').fetchall()\n"
               "print(json.dumps({'n':len(r),'user':r[0][0],'argon':r[0][1].startswith('$argon2id$v=19$m=65536,t=3,p=4$'),'activo':r[0][2],'uid':os.stat(p).st_uid,'mode':oct(os.stat(p).st_mode&0o777),'cols':[x[1] for x in c.execute('pragma table_info(admins)')]}))")
    facts = json.loads(probe.stdout)
    check("SQLite inicializada con UN administrador activo (hash Argon2id)", facts["n"] == 1 and facts["argon"] and facts["activo"] == 1 and facts["user"] == a.username, f"usuario={facts['user']}")
    check("archivo de la base del usuario sin privilegios y modo 0600", facts["uid"] == 10001 and facts["mode"] == "0o600", f"uid={facts['uid']} modo={facts['mode']}")
    check("la base no tiene columnas de claves, tokens ni secretos", not [c for c in facts["cols"] if any(w in c for w in ("key", "token", "jwt", "cookie", "secret", "nsec"))])
    with tempfile.TemporaryDirectory() as tmp:
        sh("docker", "cp", f"{container}:/data/nip46.db", str(Path(tmp) / "copia.db"))
        raw = (Path(tmp) / "copia.db").read_bytes()
    check("la contraseña NO está en claro en el archivo de la base", password.encode() not in raw)

    # --- interfaz y cabeceras
    st, hd, body = call(base, "GET", "/health")
    check("GET /health 200 {status: ok}", st == 200 and json.loads(body) == {"status": "ok"})
    st, hd, body = call(base, "GET", "/")
    csp = hd.get("content-security-policy", "")
    check("interfaz accesible en localhost con CSP estricta y cabeceras de seguridad",
          st == 200 and b"login-username" in body and "default-src 'none'" in csp and "unsafe-inline" not in csp and hd.get("x-frame-options") == "DENY" and hd.get("x-content-type-options") == "nosniff")
    check("sin código de acceso de la terminal en la interfaz", b"login-code" not in body)
    check("/docs y /openapi.json deshabilitados", call(base, "GET", "/docs")[0] == 404 and call(base, "GET", "/openapi.json")[0] == 404)
    check("/api sin sesión → 401 (sonda anónima, no cuenta como fallo)", all(call(base, "GET", "/api/status")[0] == 401 for _ in range(15)))

    # --- login
    wrong, unknown = call(base, "POST", "/api/auth/login", {"username": a.username, "password": "incorrecta-" + password}), call(base, "POST", "/api/auth/login", {"username": "no-existe", "password": password})
    check("contraseña incorrecta y usuario inexistente: mismo 401 y mismo cuerpo", wrong[0] == unknown[0] == 401 and wrong[2] == unknown[2] and "set-cookie" not in wrong[1])
    st, hd, body = call(base, "POST", "/api/auth/login", {"username": a.username, "password": password})
    data = json.loads(body) if st == 200 else {}
    cookie = hd.get("set-cookie", "")
    token = cookie.split("nip46_session=")[1].split(";")[0] if "nip46_session=" in cookie else ""
    low = cookie.lower()
    check("login correcto 200", st == 200)
    check("el cuerpo visible al JavaScript NO contiene el JWT ni la contraseña", set(data) == {"csrf_token", "expires_in_s"} and token not in body.decode() and password not in body.decode(), f"campos={sorted(data)}")
    check("cookie de sesión HttpOnly, SameSite=Strict, Path=/api", "httponly" in low and "samesite=strict" in low and "path=/api" in low)
    header = json.loads(base64.urlsafe_b64decode(token.split(".")[0] + "==")) if token.count(".") == 2 else {}
    claims = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "==")) if token.count(".") == 2 else {}
    check("JWT generado por el servidor: HS256 con claims obligatorios y expiración corta", header.get("alg") == "HS256" and {"iss", "aud", "sub", "iat", "nbf", "exp", "jti", "csrf"} <= set(claims) and claims["exp"] - claims["iat"] == data.get("expires_in_s") == 900,
          f"alg={header.get('alg')} ttl={data.get('expires_in_s')}")
    sess = {"Cookie": f"nip46_session={token}"}
    check("sesión válida con la cookie (GET /api/status)", call(base, "GET", "/api/status", headers=sess)[0] == 200)

    # --- CSRF y logout
    csrf = data.get("csrf_token", "")
    no_csrf = call(base, "POST", "/api/auth/logout", headers=sess)[0]
    bad_csrf = call(base, "POST", "/api/auth/logout", headers={**sess, "X-CSRF-Token": "otro"})[0]
    evil = call(base, "POST", "/api/auth/logout", headers={**sess, "X-CSRF-Token": csrf, "Origin": "https://evil.example"})[0]
    check("CSRF: sin cabecera, con cabecera falsa y con Origin ajeno → 403", (no_csrf, bad_csrf, evil) == (403, 403, 403), f"{no_csrf}/{bad_csrf}/{evil}")
    check("logout con CSRF correcto → 204", call(base, "POST", "/api/auth/logout", headers={**sess, "X-CSRF-Token": csrf})[0] == 204)
    check("el token queda revocado en el servidor (401 tras el logout)", call(base, "GET", "/api/status", headers=sess)[0] == 401)
    check("Host ajeno rechazado (400)", call(base, "GET", "/health", headers={"Host": "evil.example"})[0] == 400)
    st, _, _ = call(base, "POST", "/api/auth/login", {"username": a.username, "password": password})
    check("nuevo login tras el logout → 200 (la sesión se deja abierta solo hasta caducar; el propietario inicia la suya)", st == 200)

    # --- registros y red
    logs = sh(*dc, "logs", "--no-color", "--no-log-prefix").stdout
    check("registros sin contraseña, hash ni JWT", password not in logs and "$argon2" not in logs and not re.search(r"eyJ[A-Za-z0-9_-]{10,}\.", logs) and token not in logs)
    events = {e for e in ("admin_bootstrap", "login_ok", "login_failed", "logout") if f"event={e}" in logs}
    check("registro operacional con los eventos de autenticación", {"login_ok", "login_failed", "logout"} <= events, ",".join(sorted(events)))
    check("sin errores ni trazas en los registros", "Traceback" not in logs and " ERROR " not in logs)
    net = sh(*dc, "exec", "-T", "app", "python", "-c",
             "import json,socket,struct,ipaddress\n"
             "out=[]\n"
             "for f in ('/proc/net/tcp','/proc/net/tcp6'):\n"
             "    try: lines=open(f).read().split('\\n')[1:]\n"
             "    except OSError: continue\n"
             "    for l in lines:\n"
             "        p=l.split()\n"
             "        if len(p)>3 and p[3]=='01':\n"
             "            h=p[2].split(':')[0]\n"
             "            ip=socket.inet_ntoa(struct.pack('<I',int(h,16))) if len(h)==8 else '::'\n"
             "            out.append(ip)\n"
             "pub=[i for i in out if i!='::' and not (ipaddress.ip_address(i).is_private or ipaddress.ip_address(i).is_loopback)]\n"
             "print(json.dumps({'establecidas':len(out),'publicas':pub}))").stdout
    n = json.loads(net)
    check("conexiones TCP establecidas del contenedor: ninguna hacia direcciones públicas", n["publicas"] == [], f"establecidas={n['establecidas']} publicas={n['publicas']}")

    fails = [r for r in RESULTS if r["resultado"] == "FAIL"]
    print(f"\nRESUMEN: {len(RESULTS) - len(fails)}/{len(RESULTS)} PASS", flush=True)
    if a.evidence:
        Path(a.evidence).write_text(json.dumps({"proyecto": a.project, "resultados": RESULTS}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
