"""Trazabilidad de sesiones de IA (D-17): exporta transcripciones de Claude Code a `docs/ai-sessions/`, comprueba que no falte nada y respalda los historiales.

SOLO biblioteca estándar. Lee los historiales JSONL locales de Claude Code (fuera del repositorio) y NUNCA los copia al repositorio.

Subcomandos (todos explícitos y reproducibles; no hay hooks de Git):
  list    Índice de mensajes del propietario de un historial (hora y primeros caracteres) para preparar el manifiesto.
  export  Genera las transcripciones del manifiesto: solo texto visible (prompts y respuestas), con redacción; se DETIENE ante cualquier duda.
  check   Compara los historiales con lo exportado y con el índice (`docs/ai-log.md`). Código de salida 1 si falta algo.
  scan    Busca patrones sensibles en archivos de texto (para revisar transcripciones antes de publicarlas).
  backup  Copia los historiales a una carpeta PRIVADA fuera del repositorio, tras comprobar que el destino es adecuado.

Criterios (los mismos de las transcripciones anteriores): se incluye el prompt del propietario (sin etiquetas `<pasted_content>`, bloques del editor ni
recordatorios del sistema) y todo el texto visible de las respuestas; las llamadas a herramientas dejan solo una línea de marcador; NO se incluyen
resultados de herramientas, razonamiento interno, notificaciones automáticas ni los resúmenes que genera la compactación del contexto.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Final

AGENT: Final = "Claude Code (extensión de VS Code"
STATUS_COMPLETE: Final = "COMPLETA (contenido visible)"
STATUS_PARTIAL: Final = "PARCIAL (la sesión de origen sigue abierta: se reexporta al cerrarla)"
DEFAULT_OPEN_MINUTES: Final = 120  # una sesión cuyo último registro es más reciente que esto se considera ABIERTA

# --------------------------------------------------------------------------------------------------------- limpieza de mensajes
_DROP_BLOCKS: Final = re.compile(r"<(system-reminder|ide_[a-z_]+|command-[a-z-]+|local-command-[a-z-]+)>.*?</\1>", re.S)  # se descartan ENTEROS
_WRAPPER: Final = re.compile(r"</?pasted_content[^>]*>")  # del texto pegado solo se quita la etiqueta: el contenido ES el prompt del propietario
_COMPACTION_PREFIX: Final = "This session is being continued from a previous conversation"


def clean_user_text(text: str) -> str:
    return _WRAPPER.sub("", _DROP_BLOCKS.sub("", text)).strip()


# --------------------------------------------------------------------------------------------------------- historial -> eventos
@dataclass(frozen=True)
class Event:
    kind: str  # prompt | queued_prompt | assistant_text | tool | interrupted | compaction | task_notification
    ts: str
    text: str = ""


@dataclass
class History:
    session: str
    events: list[Event] = field(default_factory=list)
    version: str = "desconocida"
    model: str = "desconocido"
    effort: str = "no disponible"
    last_ts: str = ""


def _texts(message: dict[str, Any]) -> list[str]:
    content = message.get("content")
    if isinstance(content, str):
        return [content]
    return [b.get("text", "") for b in (content or []) if isinstance(b, dict) and b.get("type") == "text"]


def _classify_user(text: str, flagged_compaction: bool) -> str:
    if flagged_compaction or text.startswith(_COMPACTION_PREFIX):
        return "compaction"
    if text.startswith("<task-notification"):
        return "task_notification"
    if text.startswith("[Request interrupted by user"):
        return "interrupted"
    return "prompt"


def load_history(path: Path) -> History:
    """Lee un JSONL en el ORDEN DEL ARCHIVO (es un registro secuencial; las marcas de hora de los resúmenes de compactación pueden retroceder)."""
    history = History(session=path.stem)
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = record.get("timestamp") or ""
            kind = record.get("type")
            if record.get("version"):
                history.version = str(record["version"])
            if ts and kind in ("user", "assistant"):
                history.last_ts = max(history.last_ts, ts)
            if kind == "assistant":
                message = record.get("message") or {}
                history.model = str(message.get("model") or history.model)
                history.effort = str(record.get("effort") or history.effort)
                for block in message.get("content") or []:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "text" and (block.get("text") or "").strip():
                        history.events.append(Event("assistant_text", ts, block["text"].strip()))
                    elif block.get("type") == "tool_use":
                        target = (block.get("input") or {}).get("file_path") if block.get("name") in ("Write", "Edit", "NotebookEdit") else None
                        history.events.append(Event("tool", ts, f"{block.get('name', '?')}" + (f" — {target}" if isinstance(target, str) else "")))
            elif kind == "user" and not record.get("isMeta") and not record.get("isSidechain"):
                content = (record.get("message") or {}).get("content")
                if isinstance(content, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
                    continue  # resultado de herramienta: no se exporta
                text = clean_user_text("\n".join(_texts(record.get("message") or {})))
                if text:
                    cls = _classify_user(text, bool(record.get("isCompactSummary")))
                    history.events.append(Event(cls, ts, text if cls == "prompt" else ""))
            elif kind == "attachment" and (record.get("attachment") or {}).get("type") == "queued_command":
                raw = (record["attachment"]).get("prompt")
                raw = raw if isinstance(raw, str) else "\n".join(b.get("text", "") for b in (raw or []) if isinstance(b, dict))
                text = clean_user_text(raw or "")
                if text:
                    cls = _classify_user(text, False)
                    history.events.append(Event("queued_prompt" if cls == "prompt" else cls, ts, text if cls == "prompt" else ""))
    return history


def human_prompts(history: History) -> list[Event]:
    return [e for e in history.events if e.kind in ("prompt", "queued_prompt")]


# --------------------------------------------------------------------------------------------------------- redacción y escaneo
_PRIVATE_CONTEXT: Final = re.compile(r"priv|secret|nsec|semilla|seed|identity\.key|\bsk\b|contrase|password", re.I)
_PUBLIC_CONTEXT: Final = re.compile(r"p[uú]blic|pubkey|npub|\bid\b|sha-?256|hash|huella|event|evento|reto|challenge|\bsig\b|firma|identidad|digest|vector", re.I)
_HEX64: Final = re.compile(r"(?<![0-9A-Za-z])[0-9a-fA-F]{64}(?![0-9A-Za-z])")
_ENTROPY_TOKEN: Final = re.compile(r"(?<![A-Za-z0-9+/=_-])[A-Za-z0-9+/=_-]{32,}(?![A-Za-z0-9+/=_-])")

_RULES: Final[tuple[tuple[str, re.Pattern[str], str], ...]] = (
    ("clave-privada-nsec", re.compile(r"\bnsec1[0-9a-z]{20,}", re.I), "[REDACTADO:clave-privada]"),
    ("clave-cifrada", re.compile(r"\bncryptsec1[0-9a-z]{20,}", re.I), "[REDACTADO:clave-privada]"),
    ("bloque-clave-privada", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(-----END [A-Z ]*PRIVATE KEY-----|\Z)", re.S), "[REDACTADO:clave-privada]"),
    ("uri-bunker", re.compile(r"bunker://[0-9A-Za-z]{16,}[^\s`\"'<>)\]]*", re.I), "[REDACTADO:uri-bunker]"),  # una URI real empieza por la clave pública (64 hex)
    ("secreto-de-conexion", re.compile(r"(?i)(secret=)[^\s&`\"'<>)\]]{6,}"), r"\1[REDACTADO:secreto-de-conexion]"),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{6,}"), "[REDACTADO:jwt]"),
    ("token-bearer", re.compile(r"(?i)\b(Bearer\s+)[A-Za-z0-9._~+/=-]{20,}"), r"\1[REDACTADO:token]"),
    ("hash-de-contrasena", re.compile(r"\$argon2(?:id|i|d)\$[^\s`\"'<>]+"), "[REDACTADO:hash-de-contrasena]"),
    ("token-api", re.compile(r"\b(sk-ant-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|AKIA[0-9A-Z]{16}|xox[abprs]-[A-Za-z0-9-]{10,})"), "[REDACTADO:token-api]"),
    ("contrasena", re.compile(r"(?i)\b((?:ADMIN_)?PASSWORD|contrase(?:ñ|n)a|passwd|pwd)(\s*[=:]\s*[\"']?)(?!Read-Host|\$|<|\[|\(|\{|\.\.\.)([A-Za-z0-9_+/=.\-]{10,})"), r"\1\2[REDACTADO:contrasena]"),
    # Correos reales; se ignoran los dominios RESERVADOS para ejemplos (RFC 2606) y la dirección pública de coautoría de Anthropic.
    ("correo", re.compile(r"(?<![A-Za-z0-9._%+-])(?![^@\s]+@(?:example\.(?:com|org|net)|[a-z0-9.-]*\.invalid)(?![A-Za-z0-9-]))(?!noreply@anthropic\.com)"
                          r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+"), "[REDACTADO:correo]"),
)
_USER_PATH: Final = re.compile(r"(?i)((?:[A-Z]:|/[a-z])?[\\/]{1,2}(?:Users|home)[\\/]{1,2})(?!\[REDACTADO)([^\\/\s\"'`<>|:*?,;)\]]+)")
_PROJECT_PATH: Final = re.compile(r"(?i)(?:[A-Z]:|/[a-z])?[\\/]{1,2}Users[\\/]{1,2}[^\\/\s\"'`<>|]+[\\/]{1,2}Documents[\\/]{1,2}nostr-nip46-remote-signer(?:[\\/]{1,2}|\b)")


@dataclass(frozen=True)
class Finding:
    kind: str
    severity: str  # block | review
    snippet: str


def redact(text: str, *, users: Sequence[str] = (), names: Sequence[str] = ()) -> tuple[str, Counter[str]]:
    """Aplica la redacción. Devuelve el texto y el recuento por categoría (determinista)."""
    counts: Counter[str] = Counter()

    def sub(label: str, pattern: re.Pattern[str], replacement: str, source: str) -> str:
        result, n = pattern.subn(replacement, source)
        if n:
            counts[label] += n
        return result

    text = _PROJECT_PATH.sub(lambda m: (counts.update(["ruta-del-proyecto"]) or ""), text)  # ruta absoluta del proyecto -> ruta relativa
    for label, pattern, replacement in _RULES:
        text = sub(label, pattern, replacement, text)
    text = sub("usuario-local", _USER_PATH, r"\1[REDACTADO:usuario-local]", text)
    for token in users:
        text = sub("usuario-local", re.compile(re.escape(token), re.I), "[REDACTADO:usuario-local]", text)
    for token in names:
        text = sub("autor", re.compile(re.escape(token), re.I), "[REDACTADO:autor]", text)
    return text, counts


def _entropy(token: str) -> float:
    freq = Counter(token)
    return -sum(c / len(token) * math.log2(c / len(token)) for c in freq.values())


def scan_text(text: str, *, allow_hex_prefixes: Iterable[str] = (), users: Sequence[str] = (), names: Sequence[str] = ()) -> list[Finding]:
    """Hallazgos que quedan en un texto YA redactado. `block` = formato de secreto sin redactar; `review` = duda que exige decisión humana (se detiene la exportación)."""
    findings: list[Finding] = []
    for label, pattern, _ in _RULES:
        for match in pattern.finditer(text):
            if "[REDACTADO" in match.group(0):
                continue
            findings.append(Finding(label, "block", match.group(0)[:12] + "…"))
    for match in _USER_PATH.finditer(text):
        findings.append(Finding("usuario-local", "block", match.group(0)[:24] + "…"))
    for token in (*users, *names):
        if token and re.search(re.escape(token), text, re.I):
            findings.append(Finding("dato-personal", "block", token[:3] + "…"))
    allowed = tuple(p.lower() for p in allow_hex_prefixes)
    for match in _HEX64.finditer(text):
        value = match.group(0)
        if value.lower().startswith(allowed) and allowed:
            continue
        context = text[max(0, match.start() - 70): match.end() + 25]
        if _PRIVATE_CONTEXT.search(context):
            findings.append(Finding("hex64-contexto-privado", "block", value[:8] + "…"))
        elif not _PUBLIC_CONTEXT.search(context):
            findings.append(Finding("hex64-sin-contexto", "review", value[:8] + "…"))
    for match in _ENTROPY_TOKEN.finditer(text):
        token = match.group(0)
        if _HEX64.fullmatch(token) or token.startswith("[REDACTADO"):
            continue
        if (sum(c.isupper() for c in token) >= 2 and sum(c.isdigit() for c in token) >= 2 and sum(c.islower() for c in token) >= 2 and _entropy(token) >= 4.2
                and "_" not in token and "-" not in token):
            findings.append(Finding("token-de-alta-entropia", "review", token[:8] + "…"))
    return findings


# --------------------------------------------------------------------------------------------------------- manifiesto e interacciones
@dataclass(frozen=True)
class Interaction:
    number: str
    session: str
    start_utc: str
    phase: str
    slug: str
    title: str

    def filename(self) -> str:
        return f"{self.start_utc[:10]}_claude-code_fase-{self.phase}_{self.number}-{self.slug}.md"


def load_manifest(path: Path) -> tuple[list[Interaction], dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data["interactions"]
    return [Interaction(number=i["n"], session=i["session"], start_utc=i["start_utc"], phase=i["phase"], slug=i["slug"], title=i["title"]) for i in items], data


def split_interactions(history: History, interactions: Sequence[Interaction]) -> dict[str, list[Event]]:
    """Reparte los eventos por interacción según el ORDEN del archivo: cada una empieza en el prompt cuya marca de hora indica el manifiesto."""
    mine = sorted((i for i in interactions if i.session == history.session), key=lambda i: i.start_utc)
    if not mine:
        return {}
    starts: list[int] = []
    for interaction in mine:
        index = next((n for n, e in enumerate(history.events) if e.kind in ("prompt", "queued_prompt") and e.ts == interaction.start_utc), None)
        if index is None:
            raise ValueError(f"interacción {interaction.number}: no hay un prompt con la marca {interaction.start_utc} en la sesión {history.session}")
        starts.append(index)
    if starts != sorted(starts):
        raise ValueError("el orden del manifiesto no coincide con el orden del historial")
    ends = [*starts[1:], len(history.events)]
    return {i.number: history.events[s:e] for i, s, e in zip(mine, starts, ends, strict=True)}


def session_is_open(history: History, now: datetime, open_minutes: int = DEFAULT_OPEN_MINUTES) -> bool:
    if not history.last_ts:
        return False
    last = datetime.fromisoformat(history.last_ts.replace("Z", "+00:00"))
    return now - last <= timedelta(minutes=open_minutes)


# --------------------------------------------------------------------------------------------------------- renderizado
def render(interaction: Interaction, events: Sequence[Event], history: History, *, status: str, users: Sequence[str] = (), names: Sequence[str] = ()) -> tuple[str, Counter[str]]:
    body: list[str] = []
    omitted: Counter[str] = Counter()
    last_ts = interaction.start_utc
    for event in events:
        if event.kind in ("compaction", "task_notification"):
            omitted[event.kind] += 1
            continue
        last_ts = max(last_ts, event.ts) if event.ts else last_ts
        if event.kind in ("prompt", "queued_prompt"):
            suffix = " — recibido a mitad de un turno" if event.kind == "queued_prompt" else ""
            body.append(f"## Prompt del propietario ({event.ts}){suffix}\n\n{event.text}\n")
        elif event.kind == "assistant_text":
            body.append(f"<!-- {event.ts} -->\n{event.text}\n")
        elif event.kind == "tool":
            body.append(f"> *[Llamada a herramienta: {event.text}]*\n")
        elif event.kind == "interrupted":
            body.append(f"> *[El propietario interrumpió la solicitud en curso ({event.ts})]*\n")
    text, counts = redact("\n".join(body), users=users, names=names)
    omitted_line = ""
    if omitted:
        parts = [f"{omitted['task_notification']} notificaciones automáticas de tareas en segundo plano" if omitted["task_notification"] else "",
                 f"{omitted['compaction']} resumen(es) de continuación generado(s) por la compactación del contexto" if omitted["compaction"] else ""]
        omitted_line = f" Se omiten {' y '.join(p for p in parts if p)}: no son mensajes del propietario ni del asistente."
    redactions = ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())) or "ninguna"
    header = f"""# Interacción {interaction.number}: {interaction.title}

| Campo | Valor |
|---|---|
| Fecha del primer prompt (UTC) | {interaction.start_utc} (America/Santiago = UTC-3) |
| Fase | {interaction.phase} |
| Agente | {AGENT}, versión {history.version}) |
| Modelo | {history.model} (campo `model` de los registros de sesión) |
| Nivel de razonamiento | {history.effort} (campo `effort` de los registros de sesión) |
| Sesión | {history.session} |
| Origen de la transcripción | Archivo de sesión local de Claude Code (JSONL), extraído con `tools/ai_sessions.py`; no reconstruido |
| Hasta (UTC) | {last_ts} |
| Estado | {status} |

**Qué contiene y qué no.** Prompts del propietario (sin las etiquetas `pasted_content`, los bloques del editor ni los recordatorios del sistema) y todo el texto visible de las respuestas de Claude Code, en orden. Las llamadas a herramientas se indican con una línea de marcador; su contenido y sus salidas **no** se incluyen (los archivos resultantes están en el repositorio y los resultados de las pruebas, en `docs/decisions.md`). **No se incluye razonamiento interno del modelo** ni contexto del sistema. Las marcas `<!-- fecha -->` son del archivo de sesión.{omitted_line}

**Redacción aplicada** (patrones y lectura de los hallazgos): URI `bunker://`, claves `nsec`, secretos de conexión, JWT, tokens `Bearer`, hashes de contraseña, contraseñas, correos, rutas locales, usuario local y nombre del autor. Las cadenas hexadecimales de 64 caracteres se clasifican por contexto: se conservan las claves **públicas**, los identificadores y las huellas SHA-256 necesarios para entender la evidencia (revisadas una a una) y la exportación se detiene ante cualquier duda. La ruta absoluta del proyecto se acortó a ruta relativa. Redacciones en este archivo: {redactions}.

---

"""
    return header + text.rstrip("\n") + "\n", counts


def export_one(interaction: Interaction, events: Sequence[Event], history: History, *, status: str, users: Sequence[str], names: Sequence[str],
               allow_hex_prefixes: Sequence[str]) -> tuple[str | None, list[Finding], Counter[str]]:
    document, counts = render(interaction, events, history, status=status, users=users, names=names)
    # Las cabeceras y las explicaciones contienen palabras como «contraseñas»; se escanea solo el cuerpo (tras la línea `---`).
    body = document.split("\n---\n", 1)[1]
    findings = scan_text(body, allow_hex_prefixes=allow_hex_prefixes, users=users, names=names)
    return (None if findings else document), findings, counts


# --------------------------------------------------------------------------------------------------------- comprobación
_HASTA: Final = re.compile(r"^\| Hasta \(UTC\) \| (\S+) \|$", re.M)
_STATUS_LINE: Final = re.compile(r"^\| Estado \| (.+) \|$", re.M)
_LINK: Final = re.compile(r"\]\((ai-sessions/[^)\s]+\.md)\)")


def index_problems(ai_log: Path, sessions_dir: Path) -> list[str]:
    """Correspondencia entre `docs/ai-sessions/*.md` y los enlaces del índice."""
    text = ai_log.read_text(encoding="utf-8")
    linked = {m.group(1).split("/", 1)[1] for m in _LINK.finditer(text)}
    present = {p.name for p in sessions_dir.glob("*.md")}
    return ([f"archivo sin enlace en el índice: {n}" for n in sorted(present - linked)]
            + [f"enlace del índice sin archivo: {n}" for n in sorted(linked - present)])


def check(history_dir: Path, manifest: Path, sessions_dir: Path, ai_log: Path | None, now: datetime) -> list[str]:
    interactions, data = load_manifest(manifest)
    problems: list[str] = []
    legacy_until: dict[str, str] = data.get("legacy_until_utc", {})
    exported: dict[str, tuple[str, str]] = {}
    for interaction in interactions:
        path = sessions_dir / interaction.filename()
        if path.exists():
            content = path.read_text(encoding="utf-8")
            hasta, status = _HASTA.search(content), _STATUS_LINE.search(content)
            exported[interaction.number] = (hasta.group(1) if hasta else "", status.group(1) if status else "")
        else:
            problems.append(f"interacción {interaction.number} ({interaction.session[:8]}…): FALTA el archivo {interaction.filename()}")
    for history_path in sorted(history_dir.glob("*.jsonl")):
        history = load_history(history_path)
        prompts = human_prompts(history)
        limit = legacy_until.get(history.session, "")
        mine = sorted((i for i in interactions if i.session == history.session), key=lambda i: i.start_utc)
        covered_until = max((exported[i.number][0] for i in mine if i.number in exported), default=limit)
        if history.session not in legacy_until and not mine:
            problems.append(f"sesión {history.session[:8]}…: {len(prompts)} prompts y NINGUNA interacción en el manifiesto")
            continue
        newer = [p for p in prompts if p.ts > max(limit, covered_until)]
        if newer:
            problems.append(f"sesión {history.session[:8]}…: {len(newer)} prompt(s) posteriores a lo exportado (primero: {newer[0].ts}); falta una interacción en el manifiesto o reexportar")
        for i in mine:
            if i.number in exported and exported[i.number][1].startswith("PARCIAL") and history.last_ts > exported[i.number][0] and i is mine[-1]:
                problems.append(f"interacción {i.number}: PARCIAL y desactualizada (hasta {exported[i.number][0]}, el historial llega a {history.last_ts})")
        if mine and not session_is_open(history, now) and any(exported.get(i.number, ("", ""))[1].startswith("PARCIAL") for i in mine):
            problems.append(f"sesión {history.session[:8]}…: está CERRADA pero hay transcripciones PARCIALES: reexportar")
    if ai_log is not None:
        problems += index_problems(ai_log, sessions_dir)
    return problems


# --------------------------------------------------------------------------------------------------------- respaldo privado
_SYNC_MARKERS: Final = ("onedrive", "dropbox", "google drive", "googledrive", "icloud", "box sync", "mega", "nextcloud", "sync")


def backup_destination_problems(dest: Path, repo_root: Path, history_dir: Path) -> list[str]:
    """Condiciones que debe cumplir el destino del respaldo. Lista vacía = adecuado."""
    problems: list[str] = []
    resolved = dest.resolve()
    if repo_root.resolve() in (resolved, *resolved.parents):
        problems.append("el destino está dentro del repositorio")
    if history_dir.resolve() in (resolved, *resolved.parents):
        problems.append("el destino está dentro de la carpeta de historiales")
    for parent in (resolved, *resolved.parents):
        if (parent / ".git").exists():
            problems.append(f"el destino está bajo un repositorio Git ({parent.name})")
            break
    for parent in (resolved, *resolved.parents):
        name = parent.name.lower()
        if any(marker in name for marker in _SYNC_MARKERS):
            problems.append(f"el destino está en una carpeta con aspecto de sincronización ({parent.name})")
    for key in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        root = os.environ.get(key)
        if root and Path(root).resolve() in (resolved, *resolved.parents):
            problems.append(f"el destino está bajo {key}")
    home = Path.home().resolve()
    if home not in resolved.parents:
        problems.append("el destino no está dentro del perfil del usuario")
    return problems


def restrict_permissions(path: Path) -> list[str]:
    """Deja el directorio accesible SOLO para el usuario actual. Devuelve problemas (lista vacía = verificado)."""
    if os.name == "nt":
        user = os.environ.get("USERNAME", "")
        domain = os.environ.get("USERDOMAIN", "")
        account = f"{domain}\\{user}" if domain and user else user
        if not account:
            return ["no se pudo determinar el usuario actual para fijar permisos"]
        done = subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r", f"{account}:(OI)(CI)F"], capture_output=True, text=True, check=False)
        if done.returncode != 0:
            return ["icacls no pudo fijar los permisos"]
        shown = subprocess.run(["icacls", str(path)], capture_output=True, text=True, check=False).stdout
        entries = [line for line in shown.splitlines() if ":(" in line]
        others = [line for line in entries if user.lower() not in line.lower()]
        return [] if entries and not others else ["los permisos resultantes incluyen a otras cuentas"]
    path.chmod(0o700)
    return [] if (path.stat().st_mode & 0o077) == 0 else ["los permisos no son 0700"]


def backup(history_dir: Path, dest: Path, repo_root: Path, stamp: str) -> tuple[Path | None, list[str]]:
    problems = backup_destination_problems(dest, repo_root, history_dir)
    if problems:
        return None, problems
    dest.mkdir(parents=True, exist_ok=True)
    problems = restrict_permissions(dest)
    if problems:
        return None, problems
    target = dest / f"snapshot-{stamp}"
    if target.exists():
        return None, [f"ya existe {target.name}: no se sobrescribe"]
    target.mkdir()
    sums: list[str] = []
    for source in sorted(history_dir.glob("*.jsonl")):
        copy = target / source.name
        shutil.copyfile(source, copy)
        sums.append(f"{hashlib.sha256(copy.read_bytes()).hexdigest()}  {copy.name}")
    (target / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
    return target, []


# --------------------------------------------------------------------------------------------------------- CLI
def _parse_now(value: str | None) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else datetime.now(timezone.utc)


def _cmd_list(args: argparse.Namespace) -> int:
    for path in sorted(Path(args.history_dir).glob("*.jsonl")):
        history = load_history(path)
        print(f"# {history.session}  (último registro {history.last_ts})")
        for n, event in enumerate(history.events):
            if event.kind in ("prompt", "queued_prompt", "interrupted", "compaction", "task_notification"):
                label = {"prompt": "prompt", "queued_prompt": "prompt (mitad de turno)"}.get(event.kind, f"[{event.kind}]")
                print(f"{event.ts}  #{n:<6} {label:24} {' '.join(event.text.split())[:70]}")
    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    interactions, data = load_manifest(Path(args.manifest))
    now = _parse_now(args.now)
    out = Path(args.out)
    wanted = set(args.only or [])
    exit_code = 0
    for history_path in sorted(Path(args.history_dir).glob("*.jsonl")):
        history = load_history(history_path)
        mine = [i for i in interactions if i.session == history.session and (not wanted or i.number in wanted)]
        if not mine:
            continue
        parts = split_interactions(history, [i for i in interactions if i.session == history.session])
        status = STATUS_PARTIAL if session_is_open(history, now, int(data.get("open_window_minutes", DEFAULT_OPEN_MINUTES))) else STATUS_COMPLETE
        for interaction in mine:
            document, findings, counts = export_one(interaction, parts[interaction.number], history, status=status, users=args.redact_user or [], names=args.redact_name or [],
                                                    allow_hex_prefixes=args.allow_hex_prefix or [])
            label = f"{interaction.number:>4} {interaction.filename()}"
            if document is None:
                exit_code = max(exit_code, 2)
                print(f"BLOQUEADA {label}: {len(findings)} hallazgo(s): " + "; ".join(sorted({f'{f.kind}({f.severity}) {f.snippet}' for f in findings})[:8]))
                continue
            target = out / interaction.filename()
            if target.exists():
                current = target.read_text(encoding="utf-8")
                if current == document:
                    print(f"SIN CAMBIOS {label}")
                    continue
                existing_status = _STATUS_LINE.search(current)
                if existing_status is None or not existing_status.group(1).startswith("PARCIAL"):
                    exit_code = max(exit_code, 3)
                    print(f"RECHAZADA {label}: ya existe y NO es PARCIAL; no se sobrescribe")
                    continue
            print(f"{'(simulacro) ' if args.dry_run else ''}ESCRIBE {label}: {len(document):,} car.; {status.split(' ')[0]}; redacciones: {dict(counts) or '-'}")
            if not args.dry_run:
                out.mkdir(parents=True, exist_ok=True)
                target.write_text(document, encoding="utf-8", newline="\n")
    return exit_code


def _cmd_check(args: argparse.Namespace) -> int:
    problems = check(Path(args.history_dir), Path(args.manifest), Path(args.out), Path(args.index) if args.index else None, _parse_now(args.now))
    for problem in problems:
        print("PENDIENTE:", problem)
    print("trazabilidad OK" if not problems else f"{len(problems)} pendiente(s)")
    return 1 if problems else 0


def _cmd_scan(args: argparse.Namespace) -> int:
    total = 0
    for name in args.paths:
        for path in sorted(Path(name).rglob("*.md")) if Path(name).is_dir() else [Path(name)]:
            findings = scan_text(path.read_text(encoding="utf-8"), allow_hex_prefixes=args.allow_hex_prefix or [], users=args.redact_user or [], names=args.redact_name or [])
            blocking = [f for f in findings if f.severity == "block"] if args.blocking_only else findings
            for f in blocking:
                print(f"{path.name}: {f.kind} ({f.severity}) {f.snippet}")
            total += len(blocking)
    print("sin hallazgos" if not total else f"{total} hallazgo(s)")
    return 1 if total else 0


def _cmd_backup(args: argparse.Namespace) -> int:
    stamp = _parse_now(args.now).strftime("%Y%m%dT%H%M%SZ")
    target, problems = backup(Path(args.history_dir), Path(args.dest), Path(args.repo_root), stamp)
    if problems:
        print("BLOQUEADO (no se copió nada):", "; ".join(problems))
        return 2
    assert target is not None
    print(f"respaldo creado en una carpeta privada fuera del repositorio ({target.name}); {len(list(target.glob('*.jsonl')))} historial(es) y SHA256SUMS")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai_sessions", description=__doc__.split("\n", 1)[0])
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser, *, history: bool = True) -> None:
        if history:
            p.add_argument("--history-dir", required=True, help="carpeta con los historiales JSONL de Claude Code (fuera del repositorio)")

    p = sub.add_parser("list", help="índice de mensajes del propietario")
    common(p)
    p = sub.add_parser("export", help="genera las transcripciones del manifiesto")
    common(p)
    p.add_argument("--manifest", default="tools/ai_sessions_manifest.json")
    p.add_argument("--out", default="docs/ai-sessions")
    p.add_argument("--only", nargs="*", help="números de interacción a exportar (por defecto, todas las del manifiesto)")
    p.add_argument("--now", help="instante de referencia ISO-8601 (por defecto, ahora): decide si la sesión está abierta")
    p.add_argument("--redact-user", action="append", help="nombre de usuario local a redactar (repetible; no se versiona)")
    p.add_argument("--redact-name", action="append", help="nombre de persona a redactar (repetible; no se versiona)")
    p.add_argument("--allow-hex-prefix", action="append", help="prefijo de una cadena de 64 hex ya revisada y pública")
    p.add_argument("--dry-run", action="store_true")
    p = sub.add_parser("check", help="compara historiales, exportaciones e índice")
    common(p)
    p.add_argument("--manifest", default="tools/ai_sessions_manifest.json")
    p.add_argument("--out", default="docs/ai-sessions")
    p.add_argument("--index", default="docs/ai-log.md")
    p.add_argument("--now")
    p = sub.add_parser("scan", help="busca patrones sensibles en archivos .md")
    p.add_argument("paths", nargs="+")
    p.add_argument("--allow-hex-prefix", action="append")
    p.add_argument("--redact-user", action="append")
    p.add_argument("--redact-name", action="append")
    p.add_argument("--blocking-only", action="store_true", help="solo formatos de secreto sin redactar (ignora las dudas por revisar)")
    p = sub.add_parser("backup", help="respaldo privado de los historiales")
    common(p)
    p.add_argument("--dest", required=True)
    p.add_argument("--repo-root", default=".")
    p.add_argument("--now")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    return {"list": _cmd_list, "export": _cmd_export, "check": _cmd_check, "scan": _cmd_scan, "backup": _cmd_backup}[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
