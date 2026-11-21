import json

import pytest

from app.nostr.keys import Keypair
from app.services.policy import CHECK_ORDER, KIND_AUTH, PolicyConfig, challenge_hash, evaluate, safe_text
from tests.support import CHALLENGE, NOW, ORIGIN, login_template

CFG = PolicyConfig(ORIGIN)
IDENT = Keypair.generate()


def run(raw: object, seen: set[str] | None = None) -> "object":
    return evaluate(raw, IDENT.public_hex, NOW, seen or set(), CFG)


def tpl(**kw: object) -> str:
    return login_template(IDENT.public_hex, **kw)  # type: ignore[arg-type]


def test_the_real_stacker_news_shape_passes_all_eleven_checks() -> None:
    result = run(tpl())
    assert result.ok and result.failed == [] and result.template is not None  # type: ignore[attr-defined]
    assert [c.name for c in result.checks] == list(CHECK_ORDER)  # type: ignore[attr-defined]
    assert result.template.kind == KIND_AUTH and result.origin_seen == ORIGIN  # type: ignore[attr-defined]
    assert result.challenge_sha16 == challenge_hash(CHALLENGE)[:16]  # type: ignore[attr-defined]


def test_template_without_id_and_pubkey_is_also_accepted() -> None:
    assert run(tpl(with_id=False)).ok  # type: ignore[attr-defined]


@pytest.mark.parametrize(("kwargs", "failed"), [
    ({"kind": 1}, "kind"),
    ({"origin": "https://evil.example"}, "origin"),
    ({"origin": "https://stacker.news/"}, "origin"),
    ({"method": "POST"}, "method"),
    ({"content": "Stacker News Authentication "}, "content"),
    ({"content": ""}, "content"),
    ({"age": 121}, "created_at"),
    ({"age": -31}, "created_at"),
    ({"challenge": "AB" * 32}, "challenge"),
    ({"challenge": "ab" * 31}, "challenge"),
    ({"challenge": "ab" * 32 + "\n"}, "challenge"),
    ({"tags": [["u", ORIGIN], ["challenge", CHALLENGE], ["method", "GET"]]}, "structure"),
    ({"tags": [["challenge", CHALLENGE], ["u", ORIGIN], ["method", "GET"], ["x", "y"]]}, "structure"),
    ({"tags": [["challenge", CHALLENGE, "extra"], ["u", ORIGIN], ["method", "GET"]]}, "structure"),
])
def test_each_deviation_is_rejected_by_the_matching_check(kwargs: dict[str, object], failed: str) -> None:
    result = run(tpl(**kwargs))
    assert not result.ok and failed in result.failed and result.template is None  # type: ignore[attr-defined]


def test_age_boundaries_are_inclusive() -> None:
    assert run(tpl(age=120)).ok and run(tpl(age=-30)).ok  # type: ignore[attr-defined]


def test_foreign_pubkey_or_forged_id_is_rejected() -> None:
    other = Keypair.generate().public_hex
    foreign = json.loads(tpl())
    foreign["pubkey"] = other
    assert "pubkey_id" in run(json.dumps(foreign)).failed  # type: ignore[attr-defined]
    forged = json.loads(tpl())
    forged["id"] = "0" * 64
    assert "pubkey_id" in run(json.dumps(forged)).failed  # type: ignore[attr-defined]
    badid = json.loads(tpl())
    badid["id"] = "zz"
    assert "pubkey_id" in run(json.dumps(badid)).failed  # type: ignore[attr-defined]


def test_replayed_challenge_is_rejected() -> None:
    assert "replay" in run(tpl(), {challenge_hash(CHALLENGE)}).failed  # type: ignore[attr-defined]


@pytest.mark.parametrize("raw", [None, 5, [], "", "{", "[]", "null", '"x"', "{}", '{"kind":27235}', "x" * 2000])
def test_garbage_input_fails_closed_and_evaluates_all_checks(raw: object) -> None:
    result = run(raw)
    assert not result.ok and result.template is None and len(result.checks) == len(CHECK_ORDER)  # type: ignore[attr-defined]


@pytest.mark.parametrize("patch", [
    {"extra": 1}, {"kind": True}, {"kind": "27235"}, {"created_at": 1.5}, {"created_at": True}, {"content": 5}, {"tags": "x"}, {"tags": [[1]]},
    {"tags": [5]}, {"kind": -1}, {"created_at": -1}, {"sig": "00"},
])
def test_schema_violations_are_rejected(patch: dict[str, object]) -> None:
    data = json.loads(tpl(with_id=False))
    data.update(patch)
    result = run(json.dumps(data))
    assert (not result.ok) or patch == {"sig": "00"}  # type: ignore[attr-defined]


def test_oversized_event_is_rejected_before_parsing() -> None:
    big = json.loads(tpl(with_id=False))
    big["content"] = "A" * 2000
    result = run(json.dumps(big))
    assert "size" in result.failed and "fields" in result.failed  # type: ignore[attr-defined]


def test_deeply_nested_json_does_not_crash() -> None:
    assert not run("[" * 500 + "]" * 500).ok  # type: ignore[attr-defined]


def test_safe_text_bounds_and_redacts() -> None:
    assert safe_text("a\x00bé") == "a?b?"
    assert safe_text("x" * 100, 10) == "x" * 10 + "..."
    for risky in ("ab" * 32, "bunker://x", "secret=abc", "nsec1qqq"):
        assert safe_text(risky) == "<redactado>"
