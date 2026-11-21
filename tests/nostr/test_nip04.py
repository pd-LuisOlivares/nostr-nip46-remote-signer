"""NIP-04 entrante: SOLO descifrar. Interoperabilidad con nostr-tools 2.16.2 (la implementación de NDK) y rutas de error."""
import base64
import os

import pytest
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from app.nostr import nip04, nip44
from app.nostr.errors import InvalidKeyError, Nip04Error
from app.nostr.keys import Keypair
from tests.nostr.helpers import nostr_tools


def encrypt_for_test(sender: Keypair, recipient_pub: str, text: bytes) -> str:
    """Cifrador SOLO de pruebas (el producto no cifra con NIP-04): permite fabricar cargas malformadas de forma controlada."""
    iv = os.urandom(16)
    padder = padding.PKCS7(128).padder()
    data = padder.update(text) + padder.finalize()
    enc = Cipher(algorithms.AES(sender.ecdh_x(recipient_pub)), modes.CBC(iv)).encryptor()
    return base64.b64encode(enc.update(data) + enc.finalize()).decode() + "?iv=" + base64.b64encode(iv).decode()


class TestInteroperability:
    def test_nostr_tools_payloads_decrypt_here(self):
        cases = nostr_tools()["nip04"]
        assert len(cases) >= 4
        for case in cases:
            assert "?iv=" in case["payload"]
            got = nip04.decrypt(Keypair.from_hex(case["recipient_sk"]), case["sender_pub"], case["payload"])
            assert got == case["plaintext"]

    def test_the_connect_request_shape_observed_with_stacker_news_decrypts(self):
        case = next(c for c in nostr_tools()["nip04"] if c["plaintext"].startswith('{"id"'))
        assert nip04.decrypt(Keypair.from_hex(case["recipient_sk"]), case["sender_pub"], case["payload"]) == case["plaintext"]

    def test_the_module_is_inbound_only(self):
        assert not hasattr(nip04, "encrypt")
        own = [n for n in dir(nip04) if not n.startswith("_") and callable(getattr(nip04, n)) and getattr(getattr(nip04, n), "__module__", "") == nip04.__name__]
        assert own == ["decrypt"]

    def test_the_shared_secret_is_the_same_unhashed_x_as_nip44(self):
        one, two = Keypair.from_hex("0" * 63 + "1"), Keypair.from_hex("0" * 63 + "2")
        assert nip44.get_conversation_key(one, two.public_hex).hex() == "c41c775356fd92eadc63ff5a0dc1da211b268cbea22316767095b2871ea1412d"


class TestErrorPaths:
    def setup_method(self):
        self.a, self.b = Keypair.generate(), Keypair.generate()
        self.good = encrypt_for_test(self.a, self.b.public_hex, b"hola")

    def test_roundtrip_with_the_test_encryptor(self):
        assert nip04.decrypt(self.b, self.a.public_hex, self.good) == "hola"

    def test_malformed_formats_are_rejected(self):
        ct, iv = self.good.split("?iv=")
        bad = ["", "sin-iv", self.good + "?iv=extra", "!!!!?iv=" + iv, ct + "?iv=!!!!", ct + "?iv=" + base64.b64encode(os.urandom(15)).decode(),
               base64.b64encode(os.urandom(17)).decode() + "?iv=" + iv, "?iv=" + iv, ct + "?iv=", "?iv=", ct.replace("=", "") + "?iv=" + iv + "A"]
        for payload in bad:
            with pytest.raises(Nip04Error):
                nip04.decrypt(self.b, self.a.public_hex, payload)
        for payload in (None, 5, b"x", ["x"]):
            with pytest.raises(Nip04Error):
                nip04.decrypt(self.b, self.a.public_hex, payload)  # type: ignore[arg-type]

    def test_oversized_payload_is_rejected_before_decoding(self):
        with pytest.raises(Nip04Error):
            nip04.decrypt(self.b, self.a.public_hex, "A" * (nip04.MAX_PAYLOAD_CHARS + 1))

    def test_wrong_key_never_returns_the_plaintext(self):
        outcomes = 0
        for _ in range(30):
            try:
                assert nip04.decrypt(Keypair.generate(), self.a.public_hex, self.good) != "hola"
            except Nip04Error:
                outcomes += 1
        assert outcomes > 0

    def test_non_utf8_plaintext_is_a_generic_error(self):
        payload = encrypt_for_test(self.a, self.b.public_hex, b"\xff\xfe\xfd")
        with pytest.raises(Nip04Error):
            nip04.decrypt(self.b, self.a.public_hex, payload)

    def test_invalid_peer_key_is_an_invalid_key_error(self):
        for bad in ("", "0" * 64, "zz" * 32):
            with pytest.raises(InvalidKeyError):
                nip04.decrypt(self.b, bad, self.good)

    def test_errors_never_reveal_the_payload(self):
        with pytest.raises(Nip04Error) as info:
            nip04.decrypt(self.b, self.a.public_hex, self.good[:-4] + "AAAA")
        assert self.good not in str(info.value) and self.good not in repr(info.value.args)

    def test_unauthenticated_tampering_is_documented_behaviour(self):
        """NIP-04 no autentica: alterar el IV puede devolver texto distinto sin error. La integridad la da la firma del evento de transporte."""
        ct, iv = self.good.split("?iv=")
        raw = bytearray(base64.b64decode(iv))
        raw[0] ^= 1
        tampered = ct + "?iv=" + base64.b64encode(bytes(raw)).decode()
        try:
            assert nip04.decrypt(self.b, self.a.public_hex, tampered) != "hola"
        except Nip04Error:
            pass
