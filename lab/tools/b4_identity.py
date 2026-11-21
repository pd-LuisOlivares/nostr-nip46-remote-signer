#!/usr/bin/env python3
"""B4: genera y custodia LA IDENTIDAD DE PRUEBA dedicada y reutilizable (decisión D-5). Herramienta de laboratorio, NO forma parte del producto.

Garantías:
  - La clave se escribe en un archivo FUERA del repositorio, con permisos restringidos, y NUNCA se imprime ni se registra.
  - Solo se muestra la clave pública (no es secreta) para poder reconocerla en la interfaz y en Stacker News.
  - `copy` la pone en el portapapeles sin mostrarla (para pegarla en «Importar una clave propia»); después hay que vaciar el portapapeles.

Uso:
  python lab/tools/b4_identity.py generate --out <ruta fuera del repositorio>
  python lab/tools/b4_identity.py pubkey   --file <ruta>
  python lab/tools/b4_identity.py copy     --file <ruta>
  python lab/tools/b4_identity.py clear-clipboard
"""
import argparse
import getpass
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from app.nostr.errors import InvalidKeyError  # noqa: E402
from app.nostr.keys import Keypair  # noqa: E402


class ToolError(Exception):
    """Error de uso (mensaje sin secretos)."""


def default_path() -> Path:
    return Path.home() / ".nip46-b4" / "identity.key"


def inside_repo(path: Path) -> bool:
    resolved = path.expanduser().resolve()
    return resolved == REPO or REPO in resolved.parents


def restrict_permissions(path: Path) -> None:
    if os.name == "nt":
        user = getpass.getuser()
        result = subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:F"], capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise ToolError("no se pudieron restringir los permisos del archivo en Windows (icacls); borre el archivo y repita")
    else:
        path.chmod(0o600)


def generate(out: Path) -> str:
    out = out.expanduser()
    if inside_repo(out):
        raise ToolError("la ruta esta DENTRO del repositorio: elija una ruta fuera (por ejemplo la de --help)")
    if out.exists():
        raise ToolError("el archivo ya existe: no se sobrescribe una identidad existente")
    out.parent.mkdir(parents=True, exist_ok=True)
    secret = secrets.token_hex(32)
    public = Keypair.from_hex(secret).public_hex  # valida que es una clave secp256k1 valida
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="ascii", newline="\n") as handle:
        handle.write(secret + "\n")
    restrict_permissions(out)
    return public


def read_key(path: Path) -> Keypair:
    path = path.expanduser()
    if inside_repo(path):
        raise ToolError("la ruta esta DENTRO del repositorio: la clave no debe estar ahi")
    if not path.is_file():
        raise ToolError("el archivo no existe")
    try:
        return Keypair.from_secret_input(path.read_text(encoding="ascii").strip())
    except (InvalidKeyError, UnicodeDecodeError):
        raise ToolError("el archivo no contiene una clave valida (64 hexadecimales o nsec)") from None


def clipboard_command() -> list[str]:
    if os.name == "nt":
        return ["clip"]
    for candidate in (["pbcopy"], ["wl-copy"], ["xclip", "-selection", "clipboard"]):
        if shutil.which(candidate[0]):
            return candidate
    raise ToolError("no hay un programa de portapapeles disponible: abra el archivo en su editor y copie la clave a mano")


def copy_to_clipboard(path: Path) -> str:
    read_key(path)  # valida antes de copiar
    text = path.expanduser().read_text(encoding="ascii").strip()
    subprocess.run(clipboard_command(), input=text, text=True, check=True)
    return Keypair.from_secret_input(text).public_hex


def clear_clipboard() -> None:
    subprocess.run(clipboard_command(), input="" if os.name != "nt" else " ", text=True, check=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    gen = sub.add_parser("generate", help="crea la identidad de prueba (no sobrescribe)")
    gen.add_argument("--out", type=Path, default=default_path(), help=f"archivo de salida FUERA del repositorio (por defecto {default_path()})")
    for name in ("pubkey", "copy"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--file", type=Path, default=default_path())
    sub.add_parser("clear-clipboard")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "generate":
            public = generate(args.out)
            print(f"Identidad creada en: {args.out.expanduser()}\nClave publica: {public}\n"
                  "La clave PRIVADA no se muestra. Guarde una copia de seguridad privada (gestor de contrasenas); si pierde el archivo, pierde la cuenta.")
        elif args.cmd == "pubkey":
            print(read_key(args.file).public_hex)
        elif args.cmd == "copy":
            public = copy_to_clipboard(args.file)
            print(f"Clave copiada al portapapeles (publica: {public}). Peguela en «Importar una clave propia» y ejecute `clear-clipboard`.")
        else:
            clear_clipboard()
            print("Portapapeles vaciado.")
    except ToolError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
