"""Eventos NIP-01: serialización canónica (contrastada con JSON.stringify de Node 22), id, firma, verificación y rechazo de malformados."""
import hashlib
import json

import pytest

from app.nostr.errors import InvalidEventError
from app.nostr.event import (MAX_CREATED_AT, NostrEvent, compute_event_id, parse_and_verify_event, parse_event, serialize_for_id,
                             sign_event, verify_event)
from app.nostr.keys import Keypair
from tests.nostr.helpers import nostr_tools

AUTH_TAGS = [["challenge", "ab" * 32], ["u", "https://stacker.news"], ["method", "GET"]]


class TestCanonicalSerialization:
    def test_matches_json_stringify_for_every_fixture(self):
        cases = nostr_tools()["serialization"]
        assert len(cases) >= 150
        for case in cases:
            tags = tuple(tuple(t) for t in case["tags"])
            got = serialize_for_id(case["pubkey"], case["created_at"], case["kind"], tags, case["content"]).decode("utf-8")
            assert got == case["expected"], repr(case["content"][:20])

    def test_every_control_character_is_covered_by_the_fixtures(self):
        contents = {c["content"] for c in nostr_tools()["serialization"]}
        assert all(any(chr(i) in content for content in contents) for i in range(32))

    def test_shape_and_escaping_examples(self):
        pub = "ab" * 32
        out = serialize_for_id(pub, 1, 1, (("t", 'a"b\\c'),), "l1\nl2\t\u0001 ñ 漢").decode("utf-8")
        assert out == '[0,"' + pub + '",1,1,[["t","a\\"b\\\\c"]],"l1\\nl2\\t\\u0001 ñ 漢"]'
        assert serialize_for_id(pub, 1, 1, (), "").decode() == '[0,"' + pub + '",1,1,[],""]'

    def test_lone_surrogates_have_no_utf8_representation_and_are_rejected(self):
        for content in ("\ud800", "a\udfffb"):
            with pytest.raises(InvalidEventError):
                serialize_for_id("ab" * 32, 1, 1, (), content)
        with pytest.raises(InvalidEventError):
            serialize_for_id("ab" * 32, 1, 1, (("t", "\ud800"),), "x")


class TestSignAndVerify:
    def test_sign_produces_a_valid_event_and_verifies(self):
        key = Keypair.generate()
        ev = sign_event(key, 27235, AUTH_TAGS, "Stacker News Authentication", 1_800_000_000)
        assert ev.pubkey == key.public_hex and ev.kind == 27235 and ev.tags[0][0] == "challenge"
        assert ev.id == compute_event_id(ev.pubkey, ev.created_at, ev.kind, ev.tags, ev.content)
        verify_event(ev)
        assert parse_and_verify_event(json.loads(ev.to_json())) == ev

    def test_known_id_for_a_fixed_event(self):
        pub = "79be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798"
        text = '[0,"' + pub + '",1700000000,1,[],"hola"]'
        assert compute_event_id(pub, 1_700_000_000, 1, (), "hola") == hashlib.sha256(text.encode()).hexdigest()

    def test_to_dict_has_exactly_the_nip01_fields_and_events_are_immutable(self):
        ev = sign_event(Keypair.generate(), 1, [["e", "x"]], "hola", 1)
        assert set(ev.to_dict()) == {"id", "pubkey", "created_at", "kind", "tags", "content", "sig"} and ev.to_dict()["tags"] == [["e", "x"]]
        with pytest.raises(AttributeError):
            ev.content = "otro"  # type: ignore[misc]

    def test_tampering_with_any_field_fails_verification(self):
        ev = sign_event(Keypair.generate(), 1, [["t", "x"]], "hola", 10)
        other = Keypair.generate()
        last = "0" if ev.sig[-1] != "0" else "1"
        tampered = [
            NostrEvent(ev.id, ev.pubkey, ev.created_at, ev.kind, ev.tags, "hola!", ev.sig),
            NostrEvent(ev.id, ev.pubkey, ev.created_at + 1, ev.kind, ev.tags, ev.content, ev.sig),
            NostrEvent(ev.id, ev.pubkey, ev.created_at, 2, ev.tags, ev.content, ev.sig),
            NostrEvent(ev.id, ev.pubkey, ev.created_at, ev.kind, (("t", "y"),), ev.content, ev.sig),
            NostrEvent(ev.id, other.public_hex, ev.created_at, ev.kind, ev.tags, ev.content, ev.sig),
            NostrEvent("0" * 64, ev.pubkey, ev.created_at, ev.kind, ev.tags, ev.content, ev.sig),
            NostrEvent(ev.id, ev.pubkey, ev.created_at, ev.kind, ev.tags, ev.content, "0" * 128),
            NostrEvent(ev.id, ev.pubkey, ev.created_at, ev.kind, ev.tags, ev.content, ev.sig[:-1] + last),
        ]
        for bad in tampered:
            with pytest.raises(InvalidEventError):
                verify_event(bad)

    def test_a_signature_from_another_key_is_rejected(self):
        a, b = Keypair.generate(), Keypair.generate()
        ev = sign_event(a, 1, [], "x", 1)
        forged = NostrEvent(ev.id, b.public_hex, ev.created_at, ev.kind, ev.tags, ev.content, ev.sig)
        with pytest.raises(InvalidEventError):
            verify_event(forged)

    def test_sign_validates_the_template(self):
        key = Keypair.generate()
        cases = ((-1, [], "x", 1), (65536, [], "x", 1), (True, [], "x", 1), (1.0, [], "x", 1), (1, "tag", "x", 1), (1, [["a", 1]], "x", 1),
                 (1, [[b"a"]], "x", 1), (1, [], b"x", 1), (1, [], None, 1), (1, [], "x", -1), (1, [], "x", MAX_CREATED_AT + 1),
                 (1, [], "x", 1.5), (1, [], "x", True), (1, None, "x", 1))
        for kind, tags, content, created in cases:
            with pytest.raises(InvalidEventError):
                sign_event(key, kind, tags, content, created)  # type: ignore[arg-type]
        assert sign_event(key, 65535, [], "", MAX_CREATED_AT).kind == 65535


class TestStrictParsing:
    def good(self) -> dict:
        return sign_event(Keypair.generate(), 27235, AUTH_TAGS, "Stacker News Authentication", 1_800_000_000).to_dict()

    def test_good_event_parses(self):
        assert isinstance(parse_event(self.good()), NostrEvent)

    @pytest.mark.parametrize("mutate", [
        lambda d: d.pop("sig"), lambda d: d.pop("id"), lambda d: d.pop("tags"), lambda d: d.update(extra="x"), lambda d: d.update(id=d["id"].upper()),
        lambda d: d.update(id=d["id"][:-1]), lambda d: d.update(pubkey="0" * 64), lambda d: d.update(pubkey=d["pubkey"].upper()),
        lambda d: d.update(sig="g" * 128), lambda d: d.update(sig=d["sig"] + "0"), lambda d: d.update(kind=True), lambda d: d.update(kind="27235"),
        lambda d: d.update(kind=1.0), lambda d: d.update(kind=-1), lambda d: d.update(created_at=True), lambda d: d.update(created_at="1"),
        lambda d: d.update(created_at=-5), lambda d: d.update(created_at=MAX_CREATED_AT + 1), lambda d: d.update(content=None), lambda d: d.update(content=5),
        lambda d: d.update(tags="x"), lambda d: d.update(tags=[["a", 1]]), lambda d: d.update(tags=["abc"]), lambda d: d.update(tags=[[None]]),
        lambda d: d.update(id=None), lambda d: d.update(pubkey=5), lambda d: d.update(sig=None), lambda d: d.update(id=d["id"] + chr(10)),
    ])
    def test_malformed_events_are_rejected(self, mutate):
        data = self.good()
        mutate(data)
        with pytest.raises(InvalidEventError):
            parse_event(data)

    @pytest.mark.parametrize("data", [None, [], "evento", 5, b"{}", {}, [("id", "x")]])
    def test_non_objects_are_rejected(self, data):
        with pytest.raises(InvalidEventError):
            parse_event(data)

    def test_parse_and_verify_rejects_a_well_formed_but_forged_event(self):
        data = self.good()
        data["content"] = "otro contenido"
        parse_event(data)
        with pytest.raises(InvalidEventError):
            parse_and_verify_event(data)

    def test_errors_do_not_echo_the_event_content(self):
        data = self.good()
        data["content"] = "contenido-sensible-123"
        data["sig"] = "0" * 128
        with pytest.raises(InvalidEventError) as info:
            parse_and_verify_event(data)
        assert "contenido-sensible-123" not in str(info.value) and "contenido-sensible-123" not in repr(info.value.args)

    def test_json_with_escapes_survives_a_roundtrip(self):
        key = Keypair.generate()
        content = 'comillas " barra \\ \n\r\t\b\f \u0000   ñ 漢 😀'
        ev = sign_event(key, 1, [["t", content]], content, 5)
        again = parse_and_verify_event(json.loads(ev.to_json()))
        assert again == ev and again.content == content
