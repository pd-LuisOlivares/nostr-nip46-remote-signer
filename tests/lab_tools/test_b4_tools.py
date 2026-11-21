"""Herramientas de laboratorio de B4 (identidad de prueba y comprobación de evidencias). No tocan red ni servicios externos."""
import importlib.util
import json
import os
import stat
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "lab" / "tools" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


identity = load("b4_identity")
evidence = load("b4_check_evidence")


def test_generate_writes_a_private_file_outside_the_repo_and_never_prints_the_secret(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "sub" / "identity.key"
    assert identity.main(["generate", "--out", str(out)]) == 0
    secret = out.read_text(encoding="ascii").strip()
    shown = capsys.readouterr()
    assert len(secret) == 64 and secret not in shown.out + shown.err
    assert identity.read_key(out).public_hex in shown.out
    if os.name != "nt":
        assert stat.S_IMODE(out.stat().st_mode) == 0o600


def test_generate_refuses_paths_inside_the_repo_and_never_overwrites(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert identity.main(["generate", "--out", str(ROOT / "identity.key")]) == 2
    assert not (ROOT / "identity.key").exists()
    out = tmp_path / "k"
    assert identity.main(["generate", "--out", str(out)]) == 0
    before = out.read_text(encoding="ascii")
    assert identity.main(["generate", "--out", str(out)]) == 2 and out.read_text(encoding="ascii") == before
    assert "DENTRO del repositorio" in capsys.readouterr().err


def test_read_key_validates_and_pubkey_command(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    good = tmp_path / "ok.key"
    good.write_text("ab" * 32 + "\n", encoding="ascii")
    assert identity.main(["pubkey", "--file", str(good)]) == 0
    assert len(capsys.readouterr().out.strip()) == 64
    for content in ("", "zz" * 32, "00" * 32, "ab" * 31):
        bad = tmp_path / "bad.key"
        bad.write_text(content, encoding="ascii")
        assert identity.main(["pubkey", "--file", str(bad)]) == 2
    assert identity.main(["pubkey", "--file", str(tmp_path / "missing")]) == 2
    assert identity.main(["pubkey", "--file", str(ROOT / "README.md")]) == 2  # dentro del repositorio


def test_copy_sends_the_key_to_the_clipboard_without_printing_it(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    key = tmp_path / "k"
    key.write_text("cd" * 32 + "\n", encoding="ascii")
    sent: list[str] = []

    def fake_run(cmd: list[str], input: str = "", **_kw: object) -> None:  # noqa: A002
        sent.append(input)

    monkeypatch.setattr(identity.subprocess, "run", fake_run)
    monkeypatch.setattr(identity, "clipboard_command", lambda: ["fake-clip"])
    assert identity.main(["copy", "--file", str(key)]) == 0
    shown = capsys.readouterr()
    assert sent == ["cd" * 32] and "cd" * 32 not in shown.out + shown.err
    assert identity.main(["clear-clipboard"]) == 0 and sent[-1].strip() == ""


def good_audit() -> dict[str, object]:
    names = ["session_start", "relay_ready", "bunker_issued", "request", "pending_created", "decision", "response_published", "request", "policy",
             "pending_created", "decision", "sign_ok", "response_published", "session_end"]
    return {"entries": [{"seq": i, "ts": 1.0, "event": n} for i, n in enumerate(names, 1)]}


def test_clean_audit_passes_the_technical_check(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "audit.json"
    path.write_text(json.dumps(good_audit()), encoding="utf-8")
    assert evidence.main(["x", str(path)]) == 0
    out = capsys.readouterr().out
    assert "sign_ok: 1" in out and "session_end: 1" in out and "COHERENTE" in out and "PASS exige ademas" in out


@pytest.mark.parametrize("leak", ["nsec1" + "q" * 20, "bunker://" + "a" * 64, "x?secret=abc", "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJvcGVyYWRvciJ9.firma123", "nip46_session=abc",
                                  "Authorization: Bearer " + "a" * 30, "a" * 64, "A" * 130])
def test_each_kind_of_leak_is_detected(tmp_path: Path, leak: str) -> None:
    data = good_audit()
    data["nota"] = leak
    path = tmp_path / "audit.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert evidence.main(["x", str(path)]) == 1


def test_incoherent_summaries_are_flagged_and_text_input_is_supported(tmp_path: Path) -> None:
    data = good_audit()
    data["entries"].append({"seq": 99, "event": "sign_ok"})  # type: ignore[attr-defined]
    data["entries"].append({"seq": 100, "event": "sign_ok"})  # type: ignore[attr-defined]
    path = tmp_path / "audit.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert evidence.main(["x", str(path)]) == 1  # mas de una firma
    text = tmp_path / "tabla.txt"
    text.write_text("1\t12:00\tsession_start\n2\t12:01\tsign_ok\n3\t12:02\tsession_end\n", encoding="utf-8")
    assert evidence.main(["x", str(text)]) == 0
    assert evidence.main(["x"]) == 2 and evidence.main(["x", str(tmp_path / "no")]) == 2
