"""NIP-44 v2: vectores oficiales (válidos e inválidos), interoperabilidad con nostr-tools 2.16.2 y propiedades."""
import base64
import hashlib
import os

import pytest

from app.nostr import nip44
from app.nostr.errors import (InvalidKeyError, InvalidLength, InvalidMac, InvalidPadding, InvalidPayload, Nip44Error, UnsupportedVersion)
from app.nostr.keys import Keypair
from tests.nostr.helpers import load_nip44_vectors, nip44_vectors_path, nostr_tools

VECTORS = load_nip44_vectors()
needs_vectors = pytest.mark.skipif(VECTORS is None, reason=f"FALTA el archivo oficial de vectores NIP-44 ({nip44_vectors_path()}); ver tests/nostr/fixtures/README.md")


def key(sec_hex: str) -> Keypair:
    return Keypair.from_hex(sec_hex)


@needs_vectors
class TestOfficialValidVectors:
    def test_get_conversation_key(self):
        for c in VECTORS["valid"]["get_conversation_key"]:
            assert nip44.get_conversation_key(key(c["sec1"]), c["pub2"]).hex() == c["conversation_key"]

    def test_get_message_keys(self):
        group = VECTORS["valid"]["get_message_keys"]
        for k in group["keys"]:
            got = nip44.get_message_keys(bytes.fromhex(group["conversation_key"]), bytes.fromhex(k["nonce"]))
            assert tuple(x.hex() for x in got) == (k["chacha_key"], k["chacha_nonce"], k["hmac_key"])

    def test_calc_padded_len(self):
        for unpadded, padded in VECTORS["valid"]["calc_padded_len"]:
            assert nip44.calc_padded_len(unpadded) == padded

    def test_encrypt_decrypt(self):
        for c in VECTORS["valid"]["encrypt_decrypt"]:
            sec1, sec2 = key(c["sec1"]), key(c["sec2"])
            k1, k2 = nip44.get_conversation_key(sec1, sec2.public_hex), nip44.get_conversation_key(sec2, sec1.public_hex)
            assert k1.hex() == k2.hex() == c["conversation_key"]
            assert nip44._encrypt_with_nonce(c["plaintext"], k1, bytes.fromhex(c["nonce"])) == c["payload"]
            assert nip44.decrypt(c["payload"], k2) == c["plaintext"]

    def test_encrypt_decrypt_long_messages(self):
        for c in VECTORS["valid"]["encrypt_decrypt_long_msg"]:
            plaintext = c["pattern"] * c["repeat"]
            assert hashlib.sha256(plaintext.encode()).hexdigest() == c["plaintext_sha256"]
            conversation_key = bytes.fromhex(c["conversation_key"])
            payload = nip44._encrypt_with_nonce(plaintext, conversation_key, bytes.fromhex(c["nonce"]))
            assert hashlib.sha256(payload.encode()).hexdigest() == c["payload_sha256"]
            assert nip44.decrypt(payload, conversation_key) == plaintext


@needs_vectors
class TestOfficialInvalidVectors:
    def test_invalid_message_lengths_are_rejected(self):
        """El archivo marca 0, 65536, 100000 y 10000000 como inválidos: coincide con el límite provisional P-14."""
        assert set(VECTORS["invalid"]["encrypt_msg_lengths"]) >= {0, 65536}
        for n in VECTORS["invalid"]["encrypt_msg_lengths"]:
            with pytest.raises(InvalidLength):
                nip44.pad("a" * n)

    def test_invalid_conversation_keys_are_rejected(self):
        for c in VECTORS["invalid"]["get_conversation_key"]:
            with pytest.raises(InvalidKeyError):
                nip44.get_conversation_key(key(c["sec1"]), c["pub2"])

    def test_invalid_decrypt_vectors_map_to_the_expected_error(self):
        expected = {"unknown encryption version": UnsupportedVersion, "unknown encryption version 0": UnsupportedVersion, "invalid base64": InvalidPayload,
                    "invalid MAC": InvalidMac, "invalid padding": InvalidPadding}
        for c in VECTORS["invalid"]["decrypt"]:
            note = c["note"]
            error = (InvalidPayload, UnsupportedVersion) if note.startswith("invalid payload length") else expected[note]
            with pytest.raises(error) as info:
                nip44.decrypt(c["payload"], bytes.fromhex(c["conversation_key"]))
            assert len(c["payload"]) < 8 or c["payload"] not in str(info.value)


class TestInteroperabilityWithNostrTools:
    def test_payloads_encrypted_by_nostr_tools_decrypt_here(self):
        for case in nostr_tools()["nip44"]:
            conversation = nip44.get_conversation_key(Keypair.from_hex(case["recipient_sk"]), case["sender_pub"])
            assert nip44.decrypt(case["payload"], conversation) == case["plaintext"]

    def test_our_payloads_have_version_2_and_decrypt_in_both_directions(self):
        a, b = Keypair.generate(), Keypair.generate()
        payload = nip44.encrypt("hola ñandú 😀", nip44.get_conversation_key(a, b.public_hex))
        assert base64.b64decode(payload)[0] == 2
        assert nip44.decrypt(payload, nip44.get_conversation_key(b, a.public_hex)) == "hola ñandú 😀"


class TestProperties:
    def setup_method(self):
        self.a, self.b = Keypair.generate(), Keypair.generate()
        self.ka = nip44.get_conversation_key(self.a, self.b.public_hex)
        self.kb = nip44.get_conversation_key(self.b, self.a.public_hex)

    def test_conversation_key_is_symmetric(self):
        assert self.ka == self.kb and len(self.ka) == 32

    def test_roundtrip_unicode_and_limits(self):
        for text in ("a", "ñandú 漢字 😀", "x" * 32, "x" * 33, "y" * 1000, "z" * nip44.MAX_PLAINTEXT):
            assert nip44.decrypt(nip44.encrypt(text, self.ka), self.kb) == text

    def test_length_limits(self):
        for bad in ("", "a" * (nip44.MAX_PLAINTEXT + 1)):
            with pytest.raises(InvalidLength):
                nip44.encrypt(bad, self.ka)

    def test_each_encryption_uses_a_fresh_nonce(self):
        assert nip44.encrypt("igual", self.ka) != nip44.encrypt("igual", self.ka)

    def test_flipping_any_byte_of_the_payload_fails(self):
        raw = bytearray(base64.b64decode(nip44.encrypt("mensaje de prueba", self.ka)))
        for i in range(len(raw)):
            mutated = bytearray(raw)
            mutated[i] ^= 1
            with pytest.raises(Nip44Error):
                nip44.decrypt(base64.b64encode(bytes(mutated)).decode(), self.kb)

    def test_wrong_key_fails_the_mac_without_leaking_plaintext(self):
        payload = nip44.encrypt("texto-secreto-xyz", self.ka)
        with pytest.raises(InvalidMac) as info:
            nip44.decrypt(payload, nip44.get_conversation_key(Keypair.generate(), self.a.public_hex))
        assert "texto-secreto-xyz" not in str(info.value) and payload not in str(info.value)

    def test_random_garbage_only_produces_domain_errors(self):
        for n in (0, 1, 50, 98, 99, 100, 200, 1000):
            for text in (base64.b64encode(os.urandom(n)).decode(), "#" + "A" * n, "?" * n, "A" * n):
                with pytest.raises(Nip44Error):
                    nip44.decrypt(text, self.ka)
        for bad in (None, 5, b"x", ["x"]):
            with pytest.raises(Nip44Error):
                nip44.decrypt(bad, self.ka)  # type: ignore[arg-type]

    def test_invalid_key_material_is_rejected(self):
        for ck, nonce in ((b"", os.urandom(32)), (os.urandom(31), os.urandom(32)), (os.urandom(32), os.urandom(31))):
            with pytest.raises(InvalidPayload):
                nip44.get_message_keys(ck, nonce)
        with pytest.raises(InvalidKeyError):
            nip44.get_conversation_key(self.a, "0" * 64)

    def test_unpad_rejects_inconsistent_padding(self):
        good = nip44.pad("hola")
        assert nip44.unpad(good) == "hola"
        for bad in (b"", b"\x00", b"\x00\x00" + b"\x00" * 32, good[:-1], good + b"\x00", (40).to_bytes(2, "big") + b"x" * 10):
            with pytest.raises(InvalidPadding):
                nip44.unpad(bad)
        with pytest.raises(InvalidPadding):
            nip44.unpad((2).to_bytes(2, "big") + b"\xff\xfe" + b"\x00" * 30)
