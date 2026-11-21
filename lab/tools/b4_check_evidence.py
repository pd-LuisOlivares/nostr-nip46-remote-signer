#!/usr/bin/env python3
"""B4: verifica que la evidencia exportada de la sesión esté SANITIZADA y resume la parte técnica. Herramienta de laboratorio (no es el producto).

Entrada: el JSON de `GET /api/audit` (`{"entries": [...]}` o una lista) o el texto copiado de la tabla de auditoría de la interfaz.
Salida: hallazgos de fuga (clave, secreto bunker, JWT, cookie, reto completo, hexadecimal de 64 caracteres) y un resumen técnico.
NO decide PASS: que Stacker News muestre una sesión autenticada solo lo puede observar el propietario.

Uso:  python lab/tools/b4_check_evidence.py <archivo>
Código de salida: 0 = sin fugas y con el resumen coherente; 1 = fuga detectada; 2 = uso incorrecto.
"""
import json
import re
import sys
from pathlib import Path

LEAKS = {
    "clave privada nsec": re.compile(r"nsec1[02-9ac-hj-np-z]{10,}"),
    "URI bunker con secreto": re.compile(r"bunker://|[?&]secret=", re.IGNORECASE),
    "JWT": re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]*"),
    "cookie o cabecera de sesion": re.compile(r"nip46_session|set-cookie|authorization\s*[:=]|bearer\s+[A-Za-z0-9_.-]{20,}", re.IGNORECASE),
    "hexadecimal de 64 caracteres (clave, reto, id o firma)": re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{64}(?![0-9a-fA-F])"),
    "base64 largo (carga cifrada)": re.compile(r"[A-Za-z0-9+/]{120,}={0,2}"),
}
EVENTS = ("session_start", "relay_ready", "bunker_issued", "request", "pending_created", "decision", "policy", "sign_ok", "response_published",
          "relay_notice", "error", "session_end")


def load_events(text: str) -> list[str]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return [name for line in text.splitlines() for name in EVENTS if re.search(rf"\b{name}\b", line)]
    entries = data["entries"] if isinstance(data, dict) and "entries" in data else data
    return [str(e.get("event")) for e in entries if isinstance(e, dict)] if isinstance(entries, list) else []


def check(text: str) -> tuple[list[str], dict[str, object]]:
    findings = [f"{name}: {len(rx.findall(text))} coincidencia(s)" for name, rx in LEAKS.items() if rx.search(text)]
    events = load_events(text)
    summary: dict[str, object] = {
        "eventos": len(events), "sign_ok": events.count("sign_ok"), "session_end": events.count("session_end"),
        "connect_o_firma_pendientes": events.count("pending_created"), "errores": events.count("error"),
        "avisos_del_relay": events.count("relay_notice"),
        "politica_fallida": len(re.findall(r'"ok":\s*false', text)) if text.lstrip().startswith(("{", "[")) else None,
    }
    return findings, summary


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    path = Path(argv[1])
    if not path.is_file():
        print("Error: el archivo no existe", file=sys.stderr)
        return 2
    findings, summary = check(path.read_text(encoding="utf-8", errors="replace"))
    print("Resumen tecnico:")
    for key, value in summary.items():
        print(f"  {key}: {value}")
    if findings:
        print("FUGAS DETECTADAS (no conserve ni comparta este archivo sin redactarlo):")
        for line in findings:
            print(f"  - {line}")
        return 1
    problems = []
    if summary["session_end"] != 1:
        problems.append("debe haber exactamente un session_end")
    if summary["sign_ok"] not in (0, 1):
        problems.append("hay mas de una firma real (el tope es 1)")
    for line in problems:
        print(f"  ! {line}")
    print("Sin fugas. " + ("Resumen COHERENTE con una sesion de B4." if not problems else "Revise los puntos marcados."))
    print("Recuerde: PASS exige ademas que Stacker News muestre una sesion autenticada (observacion del propietario).")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
