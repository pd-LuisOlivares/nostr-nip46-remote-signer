"""Lectura de la contraseña INICIAL desde un archivo local (alternativa a `ADMIN_PASSWORD`). Solo se llama si aún no hay administrador."""
from pathlib import Path
from typing import Final

from app.storage.database import StorageError

MAX_SECRET_FILE_BYTES: Final = 1024


def read_password_file(path: str) -> str:
    """Devuelve el contenido sin los saltos de línea finales. Errores genéricos: ni la ruta ni el contenido aparecen en el mensaje."""
    try:
        data = Path(path).read_bytes()[: MAX_SECRET_FILE_BYTES + 1]
        if len(data) > MAX_SECRET_FILE_BYTES:
            raise StorageError("ADMIN_PASSWORD_FILE es demasiado grande")
        return data.decode("utf-8").rstrip("\r\n")
    except (OSError, UnicodeDecodeError):
        raise StorageError("no se pudo leer ADMIN_PASSWORD_FILE (revise la ruta, los permisos y que sea texto UTF-8)") from None
