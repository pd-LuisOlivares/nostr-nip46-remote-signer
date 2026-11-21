"""Descarga y verifica los artefactos del laboratorio NIP-46 (Fase 1.0A).

Solo descarga datos; NO ejecuta ni instala nada de lo descargado. Reglas:
  - solo HTTPS, solo los hosts de "hosts_permitidos" del manifiesto, sin credenciales;
  - no sigue redirecciones (si el host respondiera con una, se aborta);
  - tamano maximo por archivo acotado;
  - el hash se verifica en memoria ANTES de escribir el archivo definitivo.
Uso (solo biblioteca estandar):  python lab/tools/fetch_artifacts.py
"""
import base64
import datetime
import hashlib
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
MAN = json.loads((LAB / "deps" / "artifacts.json").read_text(encoding="utf-8"))
ALLOWED = set(MAN["hosts_permitidos"])
VENDOR = LAB / "vendor"
MAX_BYTES = 20 * 1024 * 1024


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "redireccion no permitida", headers, fp)


def fetch(url: str) -> bytes:
    u = urllib.parse.urlsplit(url)
    if u.scheme != "https" or u.hostname not in ALLOWED or u.username or u.port not in (None, 443):
        raise SystemExit(f"URL NO PERMITIDA, se aborta: {url}")
    opener = urllib.request.build_opener(_NoRedirect)
    req = urllib.request.Request(url, headers={"User-Agent": "nip46-lab-fetch"})
    with opener.open(req, timeout=60) as resp:
        data = resp.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise SystemExit(f"Tamano excesivo, se aborta: {url}")
    return data


def sri512(data: bytes) -> str:
    return "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode()


def save(dest: Path, data: bytes) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    tmp.write_bytes(data)
    tmp.replace(dest)


def main() -> int:
    prov, failures = [], 0
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")

    def handle(kind, name, url, algo, expected, dest, compute):
        nonlocal failures
        data = fetch(url)
        got = compute(data)
        ok = got == expected
        print(f"[{'OK ' if ok else 'FALLA'}] {kind:5} {name}  ({len(data)} B)")
        if not ok:
            failures += 1
            print(f"        esperado={expected}\n        obtenido={got}\n        NO se guarda el archivo")
            return
        save(dest, data)
        prov.append({"tipo": kind, "nombre": name, "url": url, "hash": f"{algo}:{expected}",
                     "bytes": len(data), "descargado_utc": now})

    for file, t in MAN["npm"]["tarballs"].items():
        handle("npm", f"{t['name']}@{t['version']}", t["url"], "sha512", t["integrity"],
               VENDOR / "npm" / file, sri512)
    for w in MAN["pypi"]:
        handle("pypi", f"{w['name']} {w['version']}", w["url"], "sha256", w["sha256"],
               VENDOR / "wheels" / w["filename"], lambda b: hashlib.sha256(b).hexdigest())
    for d in MAN["data"]:
        handle("datos", d["name"], d["url"], "sha256", d["sha256"], VENDOR / d["dest"],
               lambda b: hashlib.sha256(b).hexdigest())
    (VENDOR / "PROVENANCE.json").write_text(json.dumps(prov, indent=2), encoding="utf-8")
    print(f"\nArtefactos verificados y guardados: {len(prov)} | fallos de integridad: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
