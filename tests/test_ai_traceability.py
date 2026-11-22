"""Trazabilidad de IA (D-17): extractor `tools/ai_sessions.py`, manifiesto, índice `docs/ai-log.md` y transcripciones `docs/ai-sessions/`.

Deterministas: usan historiales SINTÉTICOS en un directorio temporal (nunca los historiales reales de Claude Code, que viven fuera del repositorio). Sin red.
Los datos «personales» de estas pruebas se construyen por concatenación y son inventados.
"""
import ast
import importlib.util
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "ai_sessions.py"
MANIFEST = ROOT / "tools" / "ai_sessions_manifest.json"
SESSIONS = ROOT / "docs" / "ai-sessions"
AI_LOG = ROOT / "docs" / "ai-log.md"
PUBLIC_B4_PREFIX = "c5a035bf14ae9793"  # clave PÚBLICA de la identidad de prueba de B4 (documentada en el repositorio)


def load_tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location("ai_sessions", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["ai_sessions"] = module
    spec.loader.exec_module(module)
    return module


tool = load_tool()
FAKE_HOME = "C:" + "\\" + "Users" + "\\" + "jane-doe"  # inventado, construido por concatenación
UNIX_HOME = "/c/" + "Users" + "/jane-doe"  # ídem: la regla de arquitectura prohíbe estas rutas como literales en el código fuente
LINUX_HOME = "/ho" + "me/jane-doe"
ESCAPED_HOME = "C:" + "\\\\" + "Users" + "\\\\" + "jane-doe"  # forma escapada de JSON
S = "s-0001"
T1, T2, T3 = "2026-11-21T10:00:00.000Z", "2026-11-21T11:00:00.000Z", "2026-11-21T12:00:00.000Z"


# ------------------------------------------------------------------------------------------------ historiales sintéticos
def rec(kind: str, ts: str, **extra: Any) -> dict[str, Any]:
    return {"type": kind, "timestamp": ts, "sessionId": S, "version": "9.9.9", **extra}


def user(ts: str, text: str, **extra: Any) -> dict[str, Any]:
    return rec("user", ts, message={"role": "user", "content": text}, **extra)


def assistant(ts: str, text: str | None = None, tool_use: dict[str, Any] | None = None) -> dict[str, Any]:
    blocks: list[dict[str, Any]] = []
    if text is not None:
        blocks.append({"type": "text", "text": text})
    if tool_use is not None:
        blocks.append({"type": "tool_use", "id": "t1", **tool_use})
    return rec("assistant", ts, effort="high", message={"role": "assistant", "model": "modelo-de-prueba", "content": blocks})


def queued(ts: str, text: str) -> dict[str, Any]:
    return rec("attachment", ts, attachment={"type": "queued_command", "prompt": text})


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n", encoding="utf-8")


def base_records() -> list[dict[str, Any]]:
    return [
        user(T1, "<ide_opened_file>archivo</ide_opened_file> Hola A"),
        assistant("2026-11-21T10:00:05.000Z", "Respuesta A1"),
        assistant("2026-11-21T10:00:06.000Z", tool_use={"name": "Write", "input": {"file_path": FAKE_HOME + "\\proyecto\\a.py"}}),
        rec("user", "2026-11-21T10:00:07.000Z", message={"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "SALIDA SECRETA " + "nsec1" + "q" * 40}]}),
        user("2026-11-21T09:00:00.000Z", "This session is being continued from a previous conversation that ran out of context. RESUMEN"),  # la hora RETROCEDE
        assistant("2026-11-21T10:00:10.000Z", "Respuesta A2"),
        queued("2026-11-21T10:30:00.000Z", "<task-notification><task-id>x</task-id></task-notification>"),
        queued("2026-11-21T10:31:00.000Z", "Mensaje a mitad de turno"),
        assistant("2026-11-21T10:31:05.000Z", "Respuesta al mensaje a mitad de turno"),
        user(T2, '<system-reminder>ruido del sistema</system-reminder><pasted_content id="7">Hola B</pasted_content>'),
        assistant("2026-11-21T11:00:05.000Z", "Respuesta B"),
        user("2026-11-21T11:00:20.000Z", "[Request interrupted by user]"),
    ]


def manifest_for(tmp_path: Path, *, extra: list[dict[str, str]] | None = None, legacy: dict[str, str] | None = None) -> Path:
    interactions = [{"n": "1", "session": S, "start_utc": T1, "phase": "9.9", "slug": "uno", "title": "Primera"},
                    {"n": "2", "session": S, "start_utc": T2, "phase": "9.9", "slug": "dos", "title": "Segunda"}, *(extra or [])]
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"version": 1, "open_window_minutes": 120, "legacy_until_utc": legacy or {}, "interactions": interactions}), encoding="utf-8")
    return path


@pytest.fixture
def world(tmp_path: Path) -> dict[str, Path]:
    history = tmp_path / "history"
    history.mkdir()
    write_jsonl(history / f"{S}.jsonl", base_records())
    out = tmp_path / "out"
    out.mkdir()
    return {"history": history, "out": out, "manifest": manifest_for(tmp_path), "tmp": tmp_path}


def run_export(world: dict[str, Path], *extra: str, now: str = "2026-11-22T12:00:00Z") -> int:
    return int(tool.main(["export", "--history-dir", str(world["history"]), "--manifest", str(world["manifest"]), "--out", str(world["out"]), "--now", now, *extra]))


# ------------------------------------------------------------------------------------------------ lectura y reparto
def test_events_are_classified_and_tool_results_never_appear(world: dict[str, Path]) -> None:
    history = tool.load_history(world["history"] / f"{S}.jsonl")
    kinds = [e.kind for e in history.events]
    assert kinds == ["prompt", "assistant_text", "tool", "compaction", "assistant_text", "task_notification", "queued_prompt", "assistant_text", "prompt",
                     "assistant_text", "interrupted"]
    assert (history.version, history.model, history.effort, history.session) == ("9.9.9", "modelo-de-prueba", "high", S)
    assert all("SECRETA" not in e.text and "nsec1" not in e.text for e in history.events)  # el resultado de la herramienta no se exporta
    assert [e.text for e in tool.human_prompts(history)] == ["Hola A", "Mensaje a mitad de turno", "Hola B"]  # sin etiquetas del editor, del sistema ni del cliente


def test_interactions_follow_the_file_order_even_when_a_compaction_timestamp_goes_backwards(world: dict[str, Path]) -> None:
    history = tool.load_history(world["history"] / f"{S}.jsonl")
    interactions, _ = tool.load_manifest(world["manifest"])
    parts = tool.split_interactions(history, interactions)
    assert [e.text for e in parts["1"] if e.kind == "assistant_text"] == ["Respuesta A1", "Respuesta A2", "Respuesta al mensaje a mitad de turno"]
    assert [e.text for e in parts["2"] if e.kind == "assistant_text"] == ["Respuesta B"]
    assert sum(len(v) for v in parts.values()) == len(history.events)  # nada se pierde ni se duplica


def test_a_manifest_start_without_a_matching_prompt_is_an_error(world: dict[str, Path], tmp_path: Path) -> None:
    bad = manifest_for(tmp_path, extra=[{"n": "3", "session": S, "start_utc": T3, "phase": "9.9", "slug": "tres", "title": "Inexistente"}])
    interactions, _ = tool.load_manifest(bad)
    with pytest.raises(ValueError, match="no hay un prompt"):
        tool.split_interactions(tool.load_history(world["history"] / f"{S}.jsonl"), interactions)


# ------------------------------------------------------------------------------------------------ renderizado
def test_the_document_has_the_established_format(world: dict[str, Path]) -> None:
    assert run_export(world) == 0
    text = (world["out"] / "2026-11-21_claude-code_fase-9.9_1-uno.md").read_text(encoding="utf-8")
    assert text.startswith("# Interacción 1: Primera\n\n| Campo | Valor |\n|---|---|\n| Fecha del primer prompt (UTC) | 2026-11-21T10:00:00.000Z (America/Santiago = UTC-3) |")
    for field in ("| Fase | 9.9 |", "versión 9.9.9)", "modelo-de-prueba (campo `model`", "high (campo `effort`", f"| Sesión | {S} |", "no reconstruido", "| Hasta (UTC) |", "| Estado |"):
        assert field in text, field
    assert "## Prompt del propietario (2026-11-21T10:00:00.000Z)\n\nHola A" in text
    assert "## Prompt del propietario (2026-11-21T10:31:00.000Z) — recibido a mitad de un turno" in text
    assert "<!-- 2026-11-21T10:00:05.000Z -->\nRespuesta A1" in text and "> *[Llamada a herramienta: Write — " in text
    assert "Se omiten 1 notificaciones automáticas" in text and "1 resumen(es) de continuación" in text
    for noise in ("ruido del sistema", "pasted_content id", "RESUMEN", "SECRETA", "ide_opened_file"):
        assert noise not in text
    second = (world["out"] / "2026-11-21_claude-code_fase-9.9_2-dos.md").read_text(encoding="utf-8")
    assert "Hola B" in second and "El propietario interrumpió la solicitud en curso (2026-11-21T11:00:20.000Z)" in second


def test_tool_markers_show_the_path_only_for_file_writes_and_the_user_is_redacted(world: dict[str, Path]) -> None:
    run_export(world)
    text = (world["out"] / "2026-11-21_claude-code_fase-9.9_1-uno.md").read_text(encoding="utf-8")
    assert "jane-doe" not in text and "[REDACTADO:usuario-local]" in text


# ------------------------------------------------------------------------------------------------ redacción
@pytest.mark.parametrize("raw, forbidden, marker", [
    ("clave " + "nsec1" + "a" * 40, "nsec1" + "a" * 10, "[REDACTADO:clave-privada]"),
    ("uri bunker://" + "ab" * 32 + "?relay=wss://r.example&secret=" + "cd" * 8, "ab" * 32, "[REDACTADO:uri-bunker]"),
    ("url ?secret=" + "ef" * 10, "ef" * 10, "secret=[REDACTADO:secreto-de-conexion]"),
    ("token " + "eyJ" + "a" * 20 + "." + "b" * 20 + "." + "c" * 20, "eyJ" + "a" * 20, "[REDACTADO:jwt]"),
    ("Authorization: Bearer " + "x" * 40, "x" * 40, "Bearer [REDACTADO:token]"),
    ("hash $" + "argon2id$v=19$m=65536,t=3,p=4$abcdEFGH$ijklMNOP", "abcdEFGH", "[REDACTADO:hash-de-contrasena]"),
    ("ADMIN_PASSWORD=" + "una-clave-larga-123", "una-clave-larga-123", "[REDACTADO:contrasena]"),
    ("contraseña: " + "otra-clave-larga-9", "otra-clave-larga-9", "[REDACTADO:contrasena]"),
    ("escribe a " + "jane" + "@" + "empresa.cl", "jane@empresa", "[REDACTADO:correo]"),
    ("ruta " + FAKE_HOME + "\\algo", "jane-doe", "C:\\Users\\[REDACTADO:usuario-local]"),
    ("ruta " + UNIX_HOME + "/algo y " + LINUX_HOME + "/x", "jane-doe", "[REDACTADO:usuario-local]"),
    ("json " + ESCAPED_HOME + "\\\\x", "jane-doe", "[REDACTADO:usuario-local]"),
    ("token api " + "sk-ant-" + "a" * 30, "a" * 20, "[REDACTADO:token-api]"),
    ("-----BEGIN " + "PRIVATE KEY-----\nMIIabc\n-----END PRIVATE KEY-----", "MIIabc", "[REDACTADO:clave-privada]"),
])
def test_every_secret_category_is_redacted_with_its_marker(raw: str, forbidden: str, marker: str) -> None:
    text, counts = tool.redact(raw)
    assert forbidden not in text and marker in text and sum(counts.values()) >= 1
    assert not [f for f in tool.scan_text(text) if f.severity == "block"]  # y el escáner no encuentra nada más


def test_placeholders_example_domains_and_the_public_coauthor_address_are_not_redacted() -> None:
    sample = ('$env:ADMIN_PASSWORD = Read-Host "Contraseña" -MaskInput; ADMIN_PASSWORD=<valor>; ADMIN_PASSWORD_FILE=ruta; you@example.com; '
              "Co-Authored-By: Claude <noreply@anthropic.com>; bunker://<clave-publica>; 'secret=' en el texto")
    text, counts = tool.redact(sample)
    assert text == sample and not counts


def test_personal_tokens_given_by_the_caller_are_redacted_and_detected_if_left() -> None:
    text, counts = tool.redact("Autor Jane Doe en el equipo jane-pc", users=["jane-pc"], names=["Jane Doe"])
    assert "Jane" not in text and "jane-pc" not in text and counts["autor"] == 1 and counts["usuario-local"] == 1
    assert [f.kind for f in tool.scan_text("queda Jane Doe aquí", names=["Jane Doe"])] == ["dato-personal"]


def test_the_project_absolute_path_becomes_relative() -> None:
    raw = FAKE_HOME + "\\Documents\\nostr-nip46-remote-signer\\app\\main.py y " + UNIX_HOME + "/Documents/nostr-nip46-remote-signer/tests"
    text, counts = tool.redact(raw)
    assert text == "app\\main.py y tests" and counts["ruta-del-proyecto"] == 2


# ------------------------------------------------------------------------------------------------ cadenas de 64 hex y alta entropía
HEX = "9f" * 32


@pytest.mark.parametrize("context, expected", [
    ("clave pública: ", []), ("el id del evento ", []), ("SHA-256 del origen: ", []), ("huella ", []),
    ("clave privada: ", ["hex64-contexto-privado"]), ("el secreto es ", ["hex64-contexto-privado"]), ("nsec en hex ", ["hex64-contexto-privado"]),
    ("valor ", ["hex64-sin-contexto"]), ("", ["hex64-sin-contexto"]),
])
def test_a_64_hex_string_is_classified_by_its_context(context: str, expected: list[str]) -> None:
    assert [f.kind for f in tool.scan_text(context + HEX)] == expected


def test_a_reviewed_public_prefix_can_be_allowed_but_only_that_prefix() -> None:
    assert tool.scan_text("valor " + HEX, allow_hex_prefixes=[HEX[:16]]) == []
    assert [f.kind for f in tool.scan_text("valor " + "ab" * 32, allow_hex_prefixes=[HEX[:16]])] == ["hex64-sin-contexto"]


def test_a_high_entropy_token_is_flagged_for_review_but_ordinary_identifiers_are_not() -> None:
    assert [f.kind for f in tool.scan_text("token Zk3Qp9XvLm2Rt7Yw5Nb8Hc4Jd6Fg1Sa0Ue")] == ["token-de-alta-entropia"]
    for ordinary in ("test_a_pending_connect_cut_by_the_failure_is_forgotten_not_left", "nostr-nip46-remote-signer_app_data_volume_name", "a" * 40):
        assert tool.scan_text(ordinary) == []


# ------------------------------------------------------------------------------------------------ exportación: parada ante la duda, idempotencia, estados
def test_an_export_is_blocked_when_a_doubt_remains_and_nothing_is_written(world: dict[str, Path], capsys: pytest.CaptureFixture[str]) -> None:
    records = base_records()
    records.insert(2, assistant("2026-11-21T10:00:05.500Z", "valor misterioso " + HEX))
    write_jsonl(world["history"] / f"{S}.jsonl", records)
    assert run_export(world) == 2
    assert "BLOQUEADA" in capsys.readouterr().out
    assert not (world["out"] / "2026-11-21_claude-code_fase-9.9_1-uno.md").exists()
    assert (world["out"] / "2026-11-21_claude-code_fase-9.9_2-dos.md").exists()  # la otra interacción, limpia, sí se exporta
    assert run_export(world, "--allow-hex-prefix", HEX[:16]) == 0 and (world["out"] / "2026-11-21_claude-code_fase-9.9_1-uno.md").exists()  # tras revisarla


def test_the_extractor_is_idempotent(world: dict[str, Path], capsys: pytest.CaptureFixture[str]) -> None:
    assert run_export(world) == 0
    first = {p.name: p.read_bytes() for p in world["out"].glob("*.md")}
    capsys.readouterr()
    assert run_export(world) == 0
    assert "SIN CAMBIOS" in capsys.readouterr().out and "ESCRIBE" not in capsys.readouterr().out
    assert {p.name: p.read_bytes() for p in world["out"].glob("*.md")} == first  # mismos bytes
    assert all(b"\r\n" not in data for data in first.values())  # fin de línea LF


def test_complete_and_partial_are_decided_by_whether_the_session_is_open(world: dict[str, Path]) -> None:
    history = tool.load_history(world["history"] / f"{S}.jsonl")  # último registro: 11:00:20Z
    last = datetime(2026, 11, 21, 11, 0, 20, tzinfo=timezone.utc)
    assert tool.session_is_open(history, last + timedelta(minutes=119)) and not tool.session_is_open(history, last + timedelta(minutes=121))
    run_export(world, now="2026-11-21T11:30:00Z")
    assert "| Estado | PARCIAL (" in (world["out"] / "2026-11-21_claude-code_fase-9.9_1-uno.md").read_text(encoding="utf-8")
    run_export(world, now="2026-11-22T12:00:00Z")  # sesión ya cerrada: las parciales se actualizan a completas
    assert "| Estado | COMPLETA (contenido visible) |" in (world["out"] / "2026-11-21_claude-code_fase-9.9_1-uno.md").read_text(encoding="utf-8")


def test_a_complete_transcript_is_never_overwritten_with_different_content(world: dict[str, Path], capsys: pytest.CaptureFixture[str]) -> None:
    run_export(world)
    target = world["out"] / "2026-11-21_claude-code_fase-9.9_1-uno.md"
    tampered = target.read_text(encoding="utf-8") + "\nAlteración manual\n"
    target.write_text(tampered, encoding="utf-8")
    capsys.readouterr()
    assert run_export(world) == 3 and "RECHAZADA" in capsys.readouterr().out
    assert target.read_text(encoding="utf-8") == tampered  # intacto


def test_a_partial_transcript_grows_when_the_session_grows(world: dict[str, Path]) -> None:
    run_export(world, now="2026-11-21T11:30:00Z")
    before = (world["out"] / "2026-11-21_claude-code_fase-9.9_2-dos.md").read_text(encoding="utf-8")
    write_jsonl(world["history"] / f"{S}.jsonl", [*base_records(), assistant("2026-11-21T11:10:00.000Z", "Más respuesta posterior")])
    assert run_export(world, now="2026-11-21T11:30:00Z") == 0
    after = (world["out"] / "2026-11-21_claude-code_fase-9.9_2-dos.md").read_text(encoding="utf-8")
    assert "Más respuesta posterior" in after and "Más respuesta posterior" not in before


def test_only_the_manifest_interactions_are_written_and_existing_files_are_not_touched(world: dict[str, Path]) -> None:
    legacy = world["out"] / "2026-11-20_claude-code_fase-0.1_01-antigua.md"
    legacy.write_text("transcripción antigua", encoding="utf-8")
    run_export(world, "--only", "2")
    assert legacy.read_text(encoding="utf-8") == "transcripción antigua"
    assert sorted(p.name for p in world["out"].glob("*.md")) == [legacy.name, "2026-11-21_claude-code_fase-9.9_2-dos.md"]


# ------------------------------------------------------------------------------------------------ comprobación (check)
def check(world: dict[str, Path], ai_log: Path | None = None, now: str = "2026-11-21T11:30:00Z") -> list[str]:
    return tool.check(world["history"], world["manifest"], world["out"], ai_log, datetime.fromisoformat(now.replace("Z", "+00:00")))


def test_check_reports_missing_transcripts_then_passes_after_exporting(world: dict[str, Path]) -> None:
    problems = check(world)
    assert sum("FALTA el archivo" in p for p in problems) == 2 and any("3 prompt(s) posteriores a lo exportado" in p for p in problems) and len(problems) == 3
    run_export(world, now="2026-11-21T11:30:00Z")
    assert check(world) == []


def test_check_detects_new_interactions_not_yet_exported(world: dict[str, Path]) -> None:
    run_export(world, now="2026-11-21T11:30:00Z")
    write_jsonl(world["history"] / f"{S}.jsonl", [*base_records(), user(T3, "Una interacción nueva"), assistant("2026-11-21T12:00:05.000Z", "Respuesta nueva")])
    problems = check(world, now="2026-11-21T12:10:00Z")
    assert any("1 prompt(s) posteriores a lo exportado" in p and T3 in p for p in problems)
    assert any("PARCIAL y desactualizada" in p for p in problems)


def test_check_detects_a_closed_session_that_still_has_partial_transcripts(world: dict[str, Path]) -> None:
    run_export(world, now="2026-11-21T11:30:00Z")
    assert any("CERRADA pero hay transcripciones PARCIALES" in p for p in check(world, now="2026-11-22T12:00:00Z"))
    run_export(world, now="2026-11-22T12:00:00Z")
    assert check(world, now="2026-11-22T12:00:00Z") == []


def test_check_knows_legacy_sessions_and_flags_unknown_ones(world: dict[str, Path], tmp_path: Path) -> None:
    other = world["history"] / "otra-sesion.jsonl"
    write_jsonl(other, [{**user("2026-11-20T10:00:00.000Z", "Antigua"), "sessionId": "otra-sesion"}])
    run_export(world, now="2026-11-21T11:30:00Z")
    assert any("NINGUNA interacción en el manifiesto" in p for p in check(world))
    world["manifest"] = manifest_for(tmp_path, legacy={"otra-sesion": "9999-12-31T00:00:00.000Z"})
    assert check(world) == []  # sus prompts son anteriores a las exportaciones ya existentes


def test_index_problems_report_files_without_link_and_links_without_file(tmp_path: Path) -> None:
    sessions = tmp_path / "ai-sessions"
    sessions.mkdir()
    (sessions / "a.md").write_text("x", encoding="utf-8")
    (sessions / "b.md").write_text("x", encoding="utf-8")
    log = tmp_path / "ai-log.md"
    log.write_text("- [a](ai-sessions/a.md) y [fantasma](ai-sessions/c.md)\n", encoding="utf-8")
    assert tool.index_problems(log, sessions) == ["archivo sin enlace en el índice: b.md", "enlace del índice sin archivo: c.md"]


# ------------------------------------------------------------------------------------------------ respaldo privado
def test_backup_refuses_unsafe_destinations(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, history = tmp_path / "repo", tmp_path / "history"
    (repo / ".git").mkdir(parents=True)
    history.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert "el destino está dentro del repositorio" in tool.backup_destination_problems(repo / "copias", repo, history)
    assert any("repositorio Git" in p for p in tool.backup_destination_problems(repo / "x", tmp_path / "otro", history))
    assert "el destino está dentro de la carpeta de historiales" in tool.backup_destination_problems(history / "copias", repo, history)
    sync = tmp_path / "OneDrive" / "copias"
    assert any("sincronización" in p for p in tool.backup_destination_problems(sync, repo, history))
    monkeypatch.setenv("OneDrive", str(tmp_path / "nube"))
    assert any("OneDrive" in p for p in tool.backup_destination_problems(tmp_path / "nube" / "x", repo, history))
    assert tool.backup_destination_problems(tmp_path / ".respaldos", repo, history) == []
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "otro-perfil"))
    assert "el destino no está dentro del perfil del usuario" in tool.backup_destination_problems(tmp_path / ".respaldos", repo, history)


def test_backup_copies_without_touching_the_originals_and_records_hashes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, history = tmp_path / "repo", tmp_path / "history"
    repo.mkdir()
    history.mkdir()
    write_jsonl(history / "a.jsonl", [user(T1, "uno")])
    original = (history / "a.jsonl").read_bytes()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(tool, "restrict_permissions", lambda path: [])
    target, problems = tool.backup(history, tmp_path / ".respaldos", repo, "20261122T000000Z")
    assert problems == [] and target is not None and (target / "a.jsonl").read_bytes() == original and (history / "a.jsonl").read_bytes() == original
    import hashlib
    assert (target / "SHA256SUMS").read_text(encoding="utf-8") == f"{hashlib.sha256(original).hexdigest()}  a.jsonl\n"
    again, problems = tool.backup(history, tmp_path / ".respaldos", repo, "20261122T000000Z")
    assert again is None and "no se sobrescribe" in problems[0]  # un respaldo existente no se pisa


def test_backup_is_blocked_when_permissions_cannot_be_guaranteed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, history = tmp_path / "repo", tmp_path / "history"
    repo.mkdir()
    history.mkdir()
    write_jsonl(history / "a.jsonl", [user(T1, "uno")])
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(tool, "restrict_permissions", lambda path: ["los permisos resultantes incluyen a otras cuentas"])
    target, problems = tool.backup(history, tmp_path / ".respaldos", repo, "20261122T000000Z")
    assert target is None and problems and not list((tmp_path / ".respaldos").glob("snapshot-*"))  # no se copió nada


# ------------------------------------------------------------------------------------------------ el repositorio real
def manifest_interactions() -> list[Any]:
    interactions, _ = tool.load_manifest(MANIFEST)
    return list(interactions)


def test_every_transcript_is_in_the_index_and_every_index_link_exists() -> None:
    assert tool.index_problems(AI_LOG, SESSIONS) == []


def test_every_manifest_interaction_has_its_file_its_index_entry_and_a_consistent_status() -> None:
    log = AI_LOG.read_text(encoding="utf-8")
    interactions = manifest_interactions()
    assert [i.number for i in interactions] == [str(n) for n in range(32, 32 + len(interactions))]  # numeración contigua desde la 32
    for interaction in interactions:
        path = SESSIONS / interaction.filename()
        assert path.exists(), interaction.filename()
        text = path.read_text(encoding="utf-8")
        assert text.startswith(f"# Interacción {interaction.number}: {interaction.title}\n"), interaction.number
        assert f"| Fecha del primer prompt (UTC) | {interaction.start_utc} " in text and f"| Sesión | {interaction.session} |" in text
        status = re.search(r"^\| Estado \| (.+) \|$", text, re.M)
        assert status is not None and status.group(1) in (tool.STATUS_COMPLETE, tool.STATUS_PARTIAL), interaction.number
        assert re.search(r"^\| Hasta \(UTC\) \| \S+ \|$", text, re.M), interaction.number
        entry = re.search(rf"^### {interaction.number}\. .*?(?=^### |\Z)", log, re.M | re.S)
        assert entry is not None, f"falta la entrada {interaction.number} en el índice"
        assert f"](ai-sessions/{interaction.filename()})" in entry.group(0), interaction.number
        expected = "Parcial" if status.group(1).startswith("PARCIAL") else "Completa"
        assert expected in entry.group(0).split("**Transcripción:**", 1)[1].split("\n", 1)[0], f"estado de la entrada {interaction.number}"


def test_no_known_sensitive_pattern_is_left_in_the_transcripts_or_the_index() -> None:
    allowed = [PUBLIC_B4_PREFIX]
    problems = []
    for path in [*sorted(SESSIONS.glob("*.md")), AI_LOG]:
        for finding in tool.scan_text(path.read_text(encoding="utf-8"), allow_hex_prefixes=allowed):
            if finding.severity == "block":
                problems.append(f"{path.name}: {finding.kind} {finding.snippet}")
    assert problems == []


def test_the_new_transcripts_have_no_doubtful_findings_at_all() -> None:
    for interaction in manifest_interactions():
        text = (SESSIONS / interaction.filename()).read_text(encoding="utf-8")
        assert tool.scan_text(text.split("\n---\n", 1)[1], allow_hex_prefixes=[PUBLIC_B4_PREFIX]) == [], interaction.number
        for leftover in ("<pasted_content", "<system-reminder", "<ide_", "<task-notification"):
            assert leftover not in text, (interaction.number, leftover)


def test_transcripts_use_lf_line_endings_and_are_valid_utf8() -> None:
    for interaction in manifest_interactions():
        data = (SESSIONS / interaction.filename()).read_bytes()
        assert b"\r\n" not in data and data.endswith(b"\n") and not data.startswith(b"\xef\xbb\xbf")
        data.decode("utf-8")


def test_the_legacy_transcripts_are_not_in_the_manifest_and_stay_where_they_are() -> None:
    names = {p.name for p in SESSIONS.glob("*.md")}
    manifest_names = {i.filename() for i in manifest_interactions()}
    legacy = names - manifest_names
    assert len(legacy) == 36 and manifest_names <= names  # las 36 anteriores (01 a 31) no las gestiona el extractor


def test_the_tool_uses_only_the_standard_library_and_contains_no_personal_data() -> None:
    tree = ast.parse(TOOL.read_text(encoding="utf-8"))
    imported = {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module} | {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert imported <= set(sys.stdlib_module_names), imported - set(sys.stdlib_module_names)
    for source in (TOOL, MANIFEST):
        assert not [f for f in tool.scan_text(source.read_text(encoding="utf-8")) if f.severity == "block" and f.kind in ("correo", "usuario-local")], source.name
    forbidden_hooks = [p for p in (ROOT / ".git" / "hooks").glob("*") if not p.name.endswith(".sample")] if (ROOT / ".git" / "hooks").exists() else []
    assert forbidden_hooks == []  # no se instalan hooks de Git: la verificación es un comando explícito
