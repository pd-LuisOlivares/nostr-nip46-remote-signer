"""Vectores oficiales de NIP-44 (positivos y negativos) contra lab_common.nip44.

El archivo es un DATO LOCAL sin versionar (licencia sin aclarar). Si falta, las pruebas FALLAN
de forma explicita: no se omiten en silencio.
"""
import hashlib
import json
import os
import unittest

from lab_common import nip44

PATH = os.environ.get("NIP44_VECTORS", "/lab/vectors/nip44.vectors.json")


def load():
    if not os.path.exists(PATH):
        raise AssertionError(f"FALTA el archivo de vectores NIP-44: {PATH}")
    with open(PATH, encoding="utf-8") as fh:
        return json.load(fh)["v2"]


class ValidVectors(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v = load()

    def test_get_conversation_key(self):
        for c in self.v["valid"]["get_conversation_key"]:
            with self.subTest(sec1=c["sec1"][:8], pub2=c["pub2"][:8]):
                key = nip44.get_conversation_key(bytes.fromhex(c["sec1"]), c["pub2"])
                self.assertEqual(key.hex(), c["conversation_key"])

    def test_get_message_keys(self):
        grp = self.v["valid"]["get_message_keys"]
        ck = bytes.fromhex(grp["conversation_key"])
        for k in grp["keys"]:
            with self.subTest(nonce=k["nonce"][:8]):
                chacha_key, chacha_nonce, hmac_key = nip44.get_message_keys(ck, bytes.fromhex(k["nonce"]))
                self.assertEqual((chacha_key.hex(), chacha_nonce.hex(), hmac_key.hex()),
                                 (k["chacha_key"], k["chacha_nonce"], k["hmac_key"]))

    def test_calc_padded_len(self):
        for unpadded, padded in self.v["valid"]["calc_padded_len"]:
            with self.subTest(unpadded=unpadded):
                self.assertEqual(nip44.calc_padded_len(unpadded), padded)

    def test_encrypt_decrypt(self):
        for c in self.v["valid"]["encrypt_decrypt"]:
            with self.subTest(sec1=c["sec1"][:8], plaintext=c["plaintext"][:12]):
                sec1, sec2 = bytes.fromhex(c["sec1"]), bytes.fromhex(c["sec2"])
                from lab_common.nostr import pubkey_of
                key1 = nip44.get_conversation_key(sec1, pubkey_of(sec2))
                key2 = nip44.get_conversation_key(sec2, pubkey_of(sec1))
                self.assertEqual(key1.hex(), c["conversation_key"])
                self.assertEqual(key2.hex(), c["conversation_key"])
                self.assertEqual(nip44.encrypt(c["plaintext"], key1, bytes.fromhex(c["nonce"])), c["payload"])
                self.assertEqual(nip44.decrypt(c["payload"], key2), c["plaintext"])

    def test_encrypt_decrypt_long_messages(self):
        for c in self.v["valid"]["encrypt_decrypt_long_msg"]:
            with self.subTest(repeat=c["repeat"]):
                plaintext = c["pattern"] * c["repeat"]
                self.assertEqual(hashlib.sha256(plaintext.encode()).hexdigest(), c["plaintext_sha256"])
                key = bytes.fromhex(c["conversation_key"])
                payload = nip44.encrypt(plaintext, key, bytes.fromhex(c["nonce"]))
                self.assertEqual(hashlib.sha256(payload.encode()).hexdigest(), c["payload_sha256"])
                self.assertEqual(nip44.decrypt(payload, key), plaintext)


class InvalidVectors(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v = load()

    def test_invalid_message_lengths_are_rejected(self):
        # El archivo marca 0, 65536, 100000 y 10000000 como invalidos. Coincide con el limite
        # PROVISIONAL del laboratorio (P-14); el texto vigente de NIP-44 permite mas (discrepancia).
        for n in self.v["invalid"]["encrypt_msg_lengths"]:
            with self.subTest(length=n):
                with self.assertRaises(nip44.InvalidLength):
                    nip44.pad("a" * n)

    def test_invalid_conversation_keys_are_rejected(self):
        for c in self.v["invalid"]["get_conversation_key"]:
            with self.subTest(note=c["note"]):
                with self.assertRaises(nip44.InvalidKey):
                    nip44.get_conversation_key(bytes.fromhex(c["sec1"]), c["pub2"])

    def test_invalid_decrypt_vectors_map_to_the_expected_error(self):
        expected = {
            "unknown encryption version": nip44.UnsupportedVersion,
            "unknown encryption version 0": nip44.UnsupportedVersion,
            "invalid base64": nip44.InvalidPayload,
            "invalid MAC": nip44.InvalidMac,
            "invalid padding": nip44.InvalidPadding,
        }
        for c in self.v["invalid"]["decrypt"]:
            with self.subTest(note=c["note"], payload=c["payload"][:10]):
                note = c["note"]
                err = (nip44.InvalidPayload, nip44.UnsupportedVersion) if note.startswith("invalid payload length") else expected[note]
                with self.assertRaises(err) as ctx:
                    nip44.decrypt(c["payload"], bytes.fromhex(c["conversation_key"]))
                self.assertNotIn("plaintext", str(ctx.exception))  # el error no filtra texto plano


class OwnProperties(unittest.TestCase):
    def test_roundtrip_random_keys_and_tamper_every_byte_fails(self):
        from lab_common.nostr import new_secret, pubkey_of
        a, b = new_secret(), new_secret()
        ka, kb = nip44.get_conversation_key(a, pubkey_of(b)), nip44.get_conversation_key(b, pubkey_of(a))
        self.assertEqual(ka, kb)
        payload = nip44.encrypt("mensaje de prueba ñ 漢 😀", ka)
        self.assertEqual(nip44.decrypt(payload, kb), "mensaje de prueba ñ 漢 😀")
        import base64
        raw = bytearray(base64.b64decode(payload))
        for i in range(len(raw)):
            mutated = bytearray(raw)
            mutated[i] ^= 0x01
            with self.assertRaises(nip44.Nip44Error):
                nip44.decrypt(base64.b64encode(bytes(mutated)).decode(), kb)

    def test_random_garbage_only_produces_domain_errors(self):
        import base64
        import os
        key = os.urandom(32)
        for n in (0, 1, 50, 98, 99, 100, 200, 1000):
            for text in (base64.b64encode(os.urandom(n)).decode(), "#" + "A" * n, "?" * n):
                with self.assertRaises(nip44.Nip44Error):
                    nip44.decrypt(text, key)


if __name__ == "__main__":
    unittest.main()
