"""NIP-46: mensajes estrictos, URI bunker:// (relay y secreto obligatorios) y ausencia de secretos en repr/errores."""
import json
import re
from urllib.parse import quote

import pytest

from app.nostr.errors import InvalidBunkerUri, InvalidNip46Message
from app.nostr.keys import Keypair
from app.nostr.nip46 import (NIP46_KIND, SUPPORTED_METHODS, BunkerUri, Nip46Request, Nip46Response, build_bunker_uri, new_connection_secret, parse_bunker_uri,
                             parse_request, parse_response, validate_relay_url, validate_secret)

PUB = Keypair.from_hex("0" * 63 + "3").public_hex
RELAY = "wss://relay.primal.net"
SECRET = "Qx3zT9kLm2PaVb7NcR4wYe"  # 22 caracteres base64url (ficticio)


class TestConstants:
    def test_kind_and_methods(self):
        assert NIP46_KIND == 24133
        assert SUPPORTED_METHODS == ("connect", "get_public_key", "sign_event", "ping")


class TestRequests:
    def test_valid_requests(self):
        req = parse_request('{"id":"abc123","method":"connect","params":["","' + SECRET + '"]}')
        assert isinstance(req, Nip46Request) and (req.id, req.method, req.params) == ("abc123", "connect", ["", SECRET])
        assert parse_request('{"id":"1","method":"get_public_key","params":[]}').params == []
        assert parse_request('{"id":"1","method":"ping"}').params == []
        assert parse_request('{"id":"1","method":"sign_event","params":["{\\"kind\\":27235}"]}').params == ['{"kind":27235}']

    @pytest.mark.parametrize("text", [
        "", "no es json", "[]", "null", "5", '"x"', "{}", '{"id":"1"}', '{"method":"ping"}', '{"id":"","method":"ping"}', '{"id":"1","method":""}',
        '{"id":1,"method":"ping"}', '{"id":"1","method":5}', '{"id":"1","method":"ping","params":"x"}', '{"id":"1","method":"ping","params":[1]}',
        '{"id":"1","method":"ping","params":[null]}', '{"id":"1","method":"ping","params":[["x"]]}', '{"id":"1","method":"ping","extra":1}',
        '{"id":"' + "a" * 65 + '","method":"ping"}', '{"id":"1","method":"' + "a" * 65 + '"}', '{"id":"1","method":"Ping"}', '{"id":"1","method":"p ing"}',
        '{"id":"1","method":"ping\\n"}', '{"id":"1","method":"ping","params":["a","b","c","d","e","f","g","h","i"]}', '{"id":"1","method":"ping",}',
        '{"id":"1","method":"ping"} x', '[{"id":"1","method":"ping"}]', "{" * 5000,
    ])
    def test_malformed_requests_are_rejected(self, text):
        with pytest.raises(InvalidNip46Message):
            parse_request(text)

    def test_non_strings_and_oversized_messages_are_rejected(self):
        for bad in (None, 5, b'{"id":"1","method":"ping"}', ["x"]):
            with pytest.raises(InvalidNip46Message):
                parse_request(bad)  # type: ignore[arg-type]
        with pytest.raises(InvalidNip46Message):
            parse_request('{"id":"1","method":"ping","params":["' + "a" * 70000 + '"]}')

    def test_errors_do_not_reproduce_the_message(self):
        with pytest.raises(InvalidNip46Message) as info:
            parse_request('{"id":"1","method":"ping","params":[5],"x":"secreto-123"}')
        assert "secreto-123" not in str(info.value) and "secreto-123" not in repr(info.value.args) and info.value.__cause__ is None

    def test_requests_are_immutable(self):
        req = parse_request('{"id":"1","method":"ping"}')
        with pytest.raises(Exception):
            req.method = "connect"  # type: ignore[misc]


class TestResponses:
    def test_ok_serialization_is_compact(self):
        assert Nip46Response.ok("1", "ack").to_json() == '{"id":"1","result":"ack"}'
        assert json.loads(Nip46Response.ok("1", "ñ 😀").to_json())["result"] == "ñ 😀" and "ñ" in Nip46Response.ok("1", "ñ").to_json()

    def test_fail_uses_the_lab_verified_shape(self):
        assert Nip46Response.fail("1", "unauthorized").to_json() == '{"id":"1","result":"error","error":"unauthorized"}'

    def test_roundtrip_and_validation(self):
        assert parse_response('{"id":"1","result":"pong"}') == Nip46Response.ok("1", "pong")
        for bad in ("", "[]", '{"id":"1"}', '{"result":"x"}', '{"id":"1","result":5}', '{"id":"1","result":"x","error":5}', '{"id":"1","result":"x","y":1}'):
            with pytest.raises(InvalidNip46Message):
                parse_response(bad)
        with pytest.raises(Exception):
            Nip46Response(id="", result="x")


class TestSecrets:
    def test_new_secrets_have_at_least_128_bits_and_are_unique(self):
        values = {new_connection_secret() for _ in range(200)}
        assert len(values) == 200
        for value in values:
            assert re.fullmatch(r"[A-Za-z0-9_-]{22}", value)          # 16 bytes en base64url sin relleno = 128 bits
            assert len(value) * 6 >= 128

    def test_validate_secret(self):
        assert validate_secret(SECRET) == SECRET
        for bad in ("", "a" * 21, "a" * 22, "ab" * 11, SECRET + "=", SECRET[:-1] + "!", SECRET + "\n", SECRET + " ", "ñ" * 22, None, 5, "x" * 129):
            with pytest.raises(InvalidBunkerUri):
                validate_secret(bad)


class TestRelays:
    @pytest.mark.parametrize("url", ["wss://relay.primal.net", "wss://relay.example.com/", "wss://relay.example.com:8443/ruta", "wss://localhost", "wss://a.b-c.d"])
    def test_valid_relays(self, url):
        assert validate_relay_url(url) == url

    @pytest.mark.parametrize("url", [
        "", "ws://relay.primal.net", "http://x.y", "https://x.y", "relay.primal.net", "wss://", "wss://user:pw@relay.x.y", "wss://user@relay.x.y",
        "wss://relay.x.y?x=1", "wss://relay.x.y#frag", "wss://relay.x.y:99999", "wss://relay.x.y:abc", "wss://-bad.x.y", "wss://bad-.x.y", "wss://a..b",
        "wss://relay x.y", "wss://relay.x.y\n", "wss://re\tlay.x.y", "wss://ñandú.cl", "wss://" + "a" * 300, "wss://[::1]", "wss://1.2.3.4:", None, 5,
    ])
    def test_invalid_relays(self, url):
        with pytest.raises(InvalidBunkerUri):
            validate_relay_url(url)

    def test_ws_is_only_allowed_when_explicitly_requested(self):
        with pytest.raises(InvalidBunkerUri):
            validate_relay_url("ws://relay-lab:7777")
        assert validate_relay_url("ws://relay-lab:7777", allow_insecure=True) == "ws://relay-lab:7777"


class TestBunkerUri:
    def test_build_and_parse_roundtrip(self):
        uri = build_bunker_uri(PUB, [RELAY], SECRET)
        assert uri == f"bunker://{PUB}?relay={quote(RELAY, safe='')}&secret={SECRET}"
        parsed = parse_bunker_uri(uri)
        assert (parsed.signer_pubkey, parsed.relays, parsed.secret) == (PUB, (RELAY,), SECRET) and parsed.to_uri() == uri

    def test_a_uri_without_secret_serializes_without_the_parameter(self):
        assert BunkerUri(PUB, (RELAY,), None).to_uri() == f"bunker://{PUB}?relay={quote(RELAY, safe='')}"

    def test_multiple_relays_keep_their_order(self):
        uri = build_bunker_uri(PUB, [RELAY, "wss://relay.example.com/x"], SECRET)
        assert parse_bunker_uri(uri).relays == (RELAY, "wss://relay.example.com/x")

    def test_generated_secret_builds_a_valid_uri(self):
        assert parse_bunker_uri(build_bunker_uri(PUB, [RELAY], new_connection_secret())).secret is not None

    def test_the_relay_is_mandatory(self):
        for relays in ([], (), "", [""], [RELAY] * 2, [f"wss://r{i}.example.com" for i in range(4)], RELAY):
            with pytest.raises(InvalidBunkerUri):
                build_bunker_uri(PUB, relays, SECRET)  # type: ignore[arg-type]
        with pytest.raises(InvalidBunkerUri):
            parse_bunker_uri(f"bunker://{PUB}?secret={SECRET}")
        with pytest.raises(InvalidBunkerUri):
            parse_bunker_uri(f"bunker://{PUB}")

    def test_the_secret_is_mandatory_for_emitted_uris_and_optional_when_parsing_with_the_flag(self):
        with pytest.raises(InvalidBunkerUri):
            parse_bunker_uri(f"bunker://{PUB}?relay={quote(RELAY, safe='')}")
        assert parse_bunker_uri(f"bunker://{PUB}?relay={quote(RELAY, safe='')}", require_secret=False).secret is None
        for bad in ("", "short", "a" * 22):
            with pytest.raises(InvalidBunkerUri):
                build_bunker_uri(PUB, [RELAY], bad)

    def test_insecure_relays_need_the_flag(self):
        with pytest.raises(InvalidBunkerUri):
            build_bunker_uri(PUB, ["ws://relay-lab:7777"], SECRET)
        uri = build_bunker_uri(PUB, ["ws://relay-lab:7777"], SECRET, allow_insecure_relays=True)
        assert parse_bunker_uri(uri, allow_insecure_relays=True).relays == ("ws://relay-lab:7777",)
        with pytest.raises(InvalidBunkerUri):
            parse_bunker_uri(uri)

    @pytest.mark.parametrize("pubkey", ["", "0" * 64, PUB.upper(), PUB[:-1], "zz" * 32, None])
    def test_invalid_signer_keys_are_rejected(self, pubkey):
        with pytest.raises(InvalidBunkerUri):
            build_bunker_uri(pubkey, [RELAY], SECRET)  # type: ignore[arg-type]

    def test_malformed_uris_are_rejected(self):
        relay = quote(RELAY, safe="")
        good = f"bunker://{PUB}?relay={relay}&secret={SECRET}"
        for bad in ("", "x", good.replace("bunker", "nostrconnect"), good.replace("bunker://", "http://"), good.replace("bunker://", "bunker:"),
                    f"bunker://{PUB}/ruta?relay={relay}&secret={SECRET}", good + "#frag", good + "&extra=1", good + "&secret=" + SECRET, good + "&relay",
                    good.replace("&secret=", "&secret"), f"bunker://user@{PUB}?relay={relay}&secret={SECRET}", f"bunker://{PUB.upper()}?relay={relay}&secret={SECRET}",
                    f"bunker://{PUB}?relay={relay}&secret={SECRET}\n", f"bunker://{PUB}?relay={relay}&secret={SECRET} ", good + "ñ", "bunker://" + "a" * 3000,
                    f"bunker://{PUB}?relay=ws%3A%2F%2Frelay.example.com&secret={SECRET}", f"bunker://{PUB}?relay={relay}&relay={relay}&secret={SECRET}",
                    f"bunker://{PUB}?relay=%00&secret={SECRET}", f"bunker://{PUB}?;relay={relay}", None, 5, b"bunker://"):
            with pytest.raises(InvalidBunkerUri):
                parse_bunker_uri(bad)  # type: ignore[arg-type]

    def test_the_secret_never_appears_in_repr_str_or_errors(self):
        uri = build_bunker_uri(PUB, [RELAY], SECRET)
        parsed = parse_bunker_uri(uri)
        assert SECRET not in repr(parsed) and SECRET not in str(BunkerUri(PUB, (RELAY,), SECRET)) and SECRET not in f"{parsed}"
        with pytest.raises(InvalidBunkerUri) as info:
            parse_bunker_uri(uri + "&extra=1")
        assert SECRET not in str(info.value) and PUB not in str(info.value) and info.value.__cause__ is None
        with pytest.raises(InvalidBunkerUri) as info2:
            build_bunker_uri(PUB, [RELAY], SECRET + "!")
        assert SECRET not in str(info2.value)
