"""Pruebas de NIP-04 heredado (capas 1 a 4 de la estrategia de la Fase 0.3).

NIP-04 no publica vectores oficiales; la interoperabilidad con nostr-tools se comprueba en E3/E5b.
"""
import base64
import os
import unittest

from lab_common import nip04, nip44
from lab_common.nostr import new_secret, pubkey_of


class Nip04Tests(unittest.TestCase):
    def setUp(self):
        self.a, self.b = new_secret(), new_secret()

    def test_roundtrip_both_directions(self):
        payload = nip04.encrypt(self.a, pubkey_of(self.b), "ñandú 漢字 😀")
        self.assertIn("?iv=", payload)
        self.assertEqual(nip04.decrypt(self.b, pubkey_of(self.a), payload), "ñandú 漢字 😀")

    def test_capa1_ecdh_uses_unhashed_x_same_as_nip44(self):
        # La coordenada X que usa NIP-04 es la misma de NIP-44: su extract debe dar la clave de los vectores.
        sec1 = bytes.fromhex("0000000000000000000000000000000000000000000000000000000000000001")
        sec2 = bytes.fromhex("0000000000000000000000000000000000000000000000000000000000000002")
        key = nip44.get_conversation_key(sec1, pubkey_of(sec2))
        self.assertEqual(key.hex(), "c41c775356fd92eadc63ff5a0dc1da211b268cbea22316767095b2871ea1412d")
        self.assertEqual(nip44.shared_x(sec1, pubkey_of(sec2)), nip44.shared_x(sec2, pubkey_of(sec1)))

    def test_capa2_malformed_formats_are_rejected(self):
        good = nip04.encrypt(self.a, pubkey_of(self.b), "x")
        ct, iv = good.split("?iv=")
        bad = ["", "sin-iv", good + "?iv=extra", "!!!!?iv=" + iv, ct + "?iv=!!!!",
               ct + "?iv=" + base64.b64encode(os.urandom(15)).decode(),
               base64.b64encode(os.urandom(17)).decode() + "?iv=" + iv,
               "?iv=" + iv]
        for payload in bad:
            with self.subTest(payload=payload[:20]):
                with self.assertRaises(nip04.Nip04Error):
                    nip04.decrypt(self.b, pubkey_of(self.a), payload)

    def test_capa3_wrong_key_does_not_yield_plaintext(self):
        payload = nip04.encrypt(self.a, pubkey_of(self.b), "secreto de prueba")
        outcomes = 0
        for _ in range(20):
            try:
                result = nip04.decrypt(new_secret(), pubkey_of(self.a), payload)
                self.assertNotEqual(result, "secreto de prueba")
            except nip04.Nip04Error:
                outcomes += 1
        self.assertGreater(outcomes, 0)  # el relleno PKCS7 invalido es la senal habitual

    def test_capa4_tampered_iv_or_ciphertext_does_not_return_original(self):
        payload = nip04.encrypt(self.a, pubkey_of(self.b), "mensaje original 1234")
        ct, iv = payload.split("?iv=")
        raw_iv = bytearray(base64.b64decode(iv))
        raw_iv[0] ^= 0x01  # NIP-04 no autentica: puede devolver texto alterado en el primer bloque
        tampered = ct + "?iv=" + base64.b64encode(bytes(raw_iv)).decode()
        try:
            self.assertNotEqual(nip04.decrypt(self.b, pubkey_of(self.a), tampered), "mensaje original 1234")
        except nip04.Nip04Error:
            pass


if __name__ == "__main__":
    unittest.main()
