"""Importa una base SQLite del administrador (p. ej. data/b62.db) al volumen /data de Docker Compose, de forma segura (D-16).

Garantias:
  - El ORIGEN no se modifica: se monta de solo lectura en un contenedor efimero y se comprueba su SHA-256 antes y despues (no se imprime el contenido).
  - Nunca sobrescribe: el destino se crea con O_EXCL; si ya existe, se aborta sin tocarlo. No existe opcion para forzar.
  - Contenedor efimero sin red, de solo lectura, sin capacidades y con el usuario sin privilegios (uid 10001).
  - Copia con la API de respaldo de SQLite (consistente), y se comprueba integridad, version de esquema y numero de administradores.
  - Se comprueban propietario y permisos del destino (uid 10001, modo 0600) y del directorio /data (uid 10001, modo 0700).
  - Si algo falla despues de crear el destino, se elimina SOLO ese archivo recien creado.
  - No lee ni imprime contrasenas, hashes ni nombres de usuario; solo cifras y estados.

Requisitos: el volumen ya existe (`docker compose ... create`), ningun contenedor lo usa en marcha, la imagen existe en local (no se descarga nada) y la base de
origen no tiene diario pendiente (`-journal`, `-wal`, `-shm`): detenga antes cualquier proceso que la use.
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Final

DEFAULT_IMAGE: Final = "nostr-nip46-remote-signer:dev"
SQLITE_MAGIC: Final = b"SQLite format 3\x00"
APP_UID: Final = 10001

_CONTAINER_CODE: Final = r"""
import json, os, sqlite3, sys
SRC, DST, DIR = "/src/source.db", "/data/nip46.db", "/data"
def out(ok, **facts):
    print(json.dumps({"ok": ok, **facts})); sys.exit(0 if ok else 3)
if os.path.lexists(DST):
    out(False, error="destination_exists")
try:
    fd = os.open(DST, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
except OSError as exc:
    out(False, error="cannot_create_destination", errno=exc.errno)
os.close(fd)
try:
    src = sqlite3.connect("file:" + SRC + "?mode=ro&immutable=1", uri=True)
    dst = sqlite3.connect(DST)
    src.backup(dst)
    facts = {
        "integrity": dst.execute("PRAGMA integrity_check").fetchone()[0],
        "user_version": [src.execute("PRAGMA user_version").fetchone()[0], dst.execute("PRAGMA user_version").fetchone()[0]],
        "admins": [src.execute("SELECT COUNT(*) FROM admins").fetchone()[0], dst.execute("SELECT COUNT(*) FROM admins").fetchone()[0]],
    }
    dst.close(); src.close()
    os.chmod(DST, 0o600)
    st, sd = os.stat(DST), os.stat(DIR)
    facts.update(uid=st.st_uid, mode=oct(st.st_mode & 0o777), dir_uid=sd.st_uid, dir_mode=oct(sd.st_mode & 0o777), whoami=os.getuid(),
                 leftovers=sorted(n for n in os.listdir(DIR) if n != "nip46.db"))
    good = (facts["integrity"] == "ok" and facts["user_version"][0] == facts["user_version"][1] and facts["admins"][0] == facts["admins"][1] >= 1
            and st.st_uid == 10001 and oct(st.st_mode & 0o777) == "0o600" and sd.st_uid == 10001 and oct(sd.st_mode & 0o777) == "0o700" and not facts["leftovers"])
except Exception as exc:
    os.unlink(DST)
    out(False, error="copy_failed", kind=type(exc).__name__)
if not good:
    os.unlink(DST)
    out(False, error="verification_failed", **facts)
out(True, **facts)
"""


class ImportRejected(Exception):
    """El importe se rechazo antes de tocar nada, o fallo y se revirtio. El mensaje no contiene secretos."""


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def docker(*args: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, check=False)


def check_source(source: Path) -> None:
    if not source.is_file() or source.is_symlink():
        raise ImportRejected("el origen no es un archivo regular")
    with source.open("rb") as handle:
        if handle.read(16) != SQLITE_MAGIC:
            raise ImportRejected("el origen no es una base SQLite")
    for suffix in ("-journal", "-wal", "-shm"):
        if source.with_name(source.name + suffix).exists():
            raise ImportRejected(f"el origen tiene un archivo {suffix} pendiente: detenga el proceso que lo usa antes de importar")


def check_docker_side(volume: str, image: str) -> None:
    if docker("volume", "inspect", volume).returncode != 0:
        raise ImportRejected("el volumen no existe: cree primero el proyecto con `docker compose ... create`")
    if docker("image", "inspect", image).returncode != 0:
        raise ImportRejected("la imagen no existe en local (esta herramienta no descarga ni construye nada)")
    users = docker("ps", "-a", "-q", "--filter", f"volume={volume}", "--filter", "status=running")
    if users.stdout.strip():
        raise ImportRejected("hay un contenedor EN MARCHA usando el volumen: detenga la instancia antes de importar")


def run_import(source: Path, volume: str, image: str) -> dict[str, object]:
    source = source.resolve()
    check_source(source)
    check_docker_side(volume, image)
    before = sha256_of(source)
    done = docker("run", "--rm", "--pull", "never", "--network", "none", "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
                  "--user", f"{APP_UID}:{APP_UID}", "--entrypoint", "python", "-v", f"{volume}:/data", "-v", f"{source}:/src/source.db:ro", image, "-c", _CONTAINER_CODE)
    after = sha256_of(source)
    if before != after:
        raise ImportRejected("ALERTA: el archivo de origen cambio durante la importacion")
    try:
        facts: dict[str, object] = json.loads(done.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        raise ImportRejected("el contenedor auxiliar no devolvio un resultado valido") from None
    if done.returncode != 0 or facts.get("ok") is not True:
        raise ImportRejected(f"importacion rechazada ({facts.get('error', 'desconocido')}); el origen no se modifico y no se dejo ningun destino parcial")
    facts["source_sha256_unchanged"] = True
    return facts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Importa una base SQLite del administrador al volumen /data de Docker Compose (sin sobrescribir).")
    parser.add_argument("--source", required=True, type=Path, help="base SQLite de origen (se monta de solo lectura), p. ej. data/b62.db")
    parser.add_argument("--volume", required=True, help="nombre completo del volumen destino, p. ej. nostr-nip46-remote-signer_app_data")
    parser.add_argument("--image", default=DEFAULT_IMAGE, help=f"imagen local del producto (por defecto {DEFAULT_IMAGE})")
    args = parser.parse_args(argv)
    try:
        facts = run_import(args.source, args.volume, args.image)
    except ImportRejected as exc:
        sys.stderr.write(f"[importacion] {exc}\n")
        return 1
    print(json.dumps(facts, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
