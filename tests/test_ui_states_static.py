"""Reglas ESTÁTICAS de la interfaz para los estados del firmante en modo continuo (D-17). Se ejecutan siempre, sin navegador."""
import re
from pathlib import Path

JS = (Path(__file__).resolve().parents[1] / "app" / "static" / "app.js").read_text(encoding="utf-8")
CSS = (Path(__file__).resolve().parents[1] / "app" / "static" / "app.css").read_text(encoding="utf-8")


def test_the_reconnecting_state_has_a_label_a_style_and_keeps_the_stop_button_enabled():
    assert "reconnecting: 'Reconectando'" in JS and ".badge.reconnecting" in CSS
    running = re.search(r"const running = \[([^\]]*)\]", JS)
    assert running is not None and "'reconnecting'" in running.group(1)  # «Detener» disponible y «Iniciar» desactivado mientras se reconecta


def test_the_exhausted_reconnection_is_explained_and_says_the_connections_are_kept():
    assert "reconexion_agotada" in JS and "sus conexiones autorizadas se conservan" in JS and "Iniciar firmante" in JS


def test_the_revoke_button_calls_the_opaque_id_endpoint_with_delete():
    assert "api('DELETE', `/api/connections/${encodeURIComponent(id)}`)" in JS and "'Revocar'" in JS
    assert "c.client" in JS and "onRevoke(c.id)" in JS  # se revoca por el id opaco, no por la clave del cliente
