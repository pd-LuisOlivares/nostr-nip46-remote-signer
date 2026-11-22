"""Autenticación del arnés frente a la API: inicia sesión con el administrador FICTICIO del laboratorio (D-9) y obtiene el JWT.

Se ejecuta DENTRO del contenedor `app`: usuario y contraseña ya están en su entorno (`ADMIN_USERNAME`, `ADMIN_PASSWORD`), que el controlador generó al azar
para esta ejecución (no son credenciales reales). `return_token` pide el JWT en el cuerpo (cliente de línea de comandos; la interfaz web nunca lo recibe).
"""
import json
import os
import urllib.request


def authenticate(base: str) -> dict[str, str]:
    body = {"username": os.environ["ADMIN_USERNAME"], "password": os.environ["ADMIN_PASSWORD"], "return_token": True}
    req = urllib.request.Request(base + "/api/auth/login", method="POST", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return {"Authorization": "Bearer " + json.loads(resp.read())["token"]}
