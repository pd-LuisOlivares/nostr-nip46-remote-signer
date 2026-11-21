"""Registro JSONL a stdout. Politica: nunca claves privadas, secretos ni texto descifrado."""
import datetime
import json
import os
import sys

ACTOR = os.environ.get("LAB_ACTOR", "py")


def emit(**fields) -> None:
    if os.environ.get("LAB_QUIET"):  # pruebas unitarias: sin ruido
        return
    rec = {"ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds"), "actor": ACTOR}
    rec.update(fields)
    sys.stdout.write(json.dumps(rec, ensure_ascii=False) + "\n")
    sys.stdout.flush()
