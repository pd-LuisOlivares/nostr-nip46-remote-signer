"""Autenticación del arnés frente a la API: canjea el código de acceso (que aporta el controlador desde el registro del contenedor) por un JWT."""
import json
import os
import urllib.request


def authenticate(base: str) -> dict[str, str]:
    req = urllib.request.Request(base + "/api/auth/login", method="POST", data=json.dumps({"code": os.environ["API_TOKEN"]}).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return {"Authorization": "Bearer " + json.loads(resp.read())["token"]}
