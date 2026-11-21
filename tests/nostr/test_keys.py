"""Claves Nostr: creación, importación hex/nsec, BIP-340, ECDH y ausencia de exposición de secretos."""
import copy
import csv
import pickle
from pathlib import Path

import pytest

from app.nostr.errors import InvalidKeyError, SigningError
from app.nostr.keys import CURVE_ORDER, Keypair, is_valid_pubkey, require_pubkey, verify_schnorr
from tests.nostr.helpers import FIXTURES as FIXTURES_DIR
from tests.nostr.helpers import nostr_tools

SECRET_1 = "0000000000000000000000000000000000000000000000000000000000000001"
PUB_1 = "79be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798"  # generador G (clave publica de la clave privada 1)
NSEC_OFFICIAL = "nsec1vl029mgpspedva04g90vltkh6fvh240zqtv9k0t9af8935ke9laqsnlfe5"  # ejemplo de NIP-19
NSEC_OFFICIAL_HEX = "67dea2ed018072d675f5415ecfaed7d2597555e202d85b3d65ea4e58d2d92ffa"
NIP19_RECIPE_PUBKEY = "7e7e9c42a91bfef19fa929e5fda1b72e0ebc1a4c1141673e2794234d86addf4e"  # npub del mismo ejemplo


class TestCreateAndImport:
    def test_generate_gives_distinct_valid_keys(self):
        a, b = Keypair.generate(), Keypair.generate()
        assert a != b
        assert is_valid_pubkey(a.public_hex) and len(a.public_hex) == 64

    def test_from_hex_derives_the_known_public_key(self):
        assert Keypair.from_hex(SECRET_1).public_hex == PUB_1

    def test_from_hex_accepts_upper_case_but_the_public_key_is_always_lower_case(self):
        k = Keypair.from_hex("B7E151628AED2A6ABF7158809CF4F3C762E7160F38B4DA56A784D9045190CFEF")
        assert k.public_hex == "dff1d77f2a671c5f36183726db2341be58feae1da2deced843240f7b502ba659"

    @pytest.mark.parametrize("bad", [
        "", "00", "g" * 64, "0" * 63, "0" * 65, " " + SECRET_1[1:], SECRET_1 + "\n", "0" * 64,        # cero
        f"{CURVE_ORDER:064x}", f"{CURVE_ORDER + 1:064x}", "f" * 64, "0x" + SECRET_1[2:], "ñ" * 64,   # >= orden, prefijos, no ASCII
    ])
    def test_from_hex_rejects_invalid_input(self, bad):
        with pytest.raises(InvalidKeyError):
            Keypair.from_hex(bad)

    @pytest.mark.parametrize("bad", [None, 1, b"x" * 32, bytearray(31), [SECRET_1]])
    def test_from_hex_rejects_non_strings(self, bad):
        with pytest.raises(InvalidKeyError):
            Keypair.from_hex(bad)  # type: ignore[arg-type]

    def test_constructor_requires_exactly_32_valid_bytes(self):
        for bad in (b"", b"\x00" * 32, b"\xff" * 32, b"\x01" * 31, "x" * 32, None):
            with pytest.raises(InvalidKeyError):
                Keypair(bad)  # type: ignore[arg-type]


class TestNsec:
    def test_official_nip19_example(self):
        assert Keypair.from_nsec(NSEC_OFFICIAL) == Keypair.from_hex(NSEC_OFFICIAL_HEX)
        assert Keypair.from_nsec(NSEC_OFFICIAL).public_hex == NIP19_RECIPE_PUBKEY

    def test_nsec_fixtures_generated_by_nostr_tools(self):
        for case in nostr_tools()["nip19"]:
            k = Keypair.from_nsec(case["nsec"])
            assert k == Keypair.from_hex(case["secret_hex"])
            assert k.public_hex == case["pubkey_hex"]

    def test_from_secret_input_dispatches_hex_and_nsec(self):
        assert Keypair.from_secret_input(SECRET_1) == Keypair.from_secret_input(nostr_tools()["nip19"][0]["nsec"])

    @pytest.mark.parametrize("bad", [
        "", "nsec1", "nsec1qqq", NSEC_OFFICIAL[:-1], NSEC_OFFICIAL[:-1] + "q", NSEC_OFFICIAL[:20] + "q" + NSEC_OFFICIAL[21:],   # corto / checksum
        NSEC_OFFICIAL.upper(), NSEC_OFFICIAL[:10] + NSEC_OFFICIAL[10:].upper(),                                              # mayusculas / mezcla
        "npub10elfcs4fr0l0r8af98jlmgdh9c8tcxjvz9qkw038js35mp4dma8qzvjptg",                                                   # npub, no nsec
        "nsec1" + "b" * 58, "nsec1" + "i" * 58, "nsec" + "1" * 59, NSEC_OFFICIAL + "q", " " + NSEC_OFFICIAL, NSEC_OFFICIAL + "\n",
        "nsec1ñ" + NSEC_OFFICIAL[6:],
    ])
    def test_invalid_nsec_is_rejected(self, bad):
        with pytest.raises(InvalidKeyError):
            Keypair.from_nsec(bad)

    @pytest.mark.parametrize("bad", [None, 5, b"nsec1", [NSEC_OFFICIAL]])
    def test_from_nsec_rejects_non_strings(self, bad):
        with pytest.raises(InvalidKeyError):
            Keypair.from_nsec(bad)  # type: ignore[arg-type]

    def test_nsec_with_a_valid_checksum_but_wrong_payload_length_is_rejected(self):
        """Un bech32 con checksum correcto pero que no codifica 32 bytes no es una clave."""
        charset = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"

        def encode(hrp: str, values: list[int]) -> str:
            def polymod(vals: list[int]) -> int:
                chk = 1
                for v in vals:
                    top = chk >> 25
                    chk = (chk & 0x1FFFFFF) << 5 ^ v
                    for i, g in enumerate((0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3)):
                        if (top >> i) & 1:
                            chk ^= g
                return chk
            expanded = [ord(c) >> 5 for c in hrp] + [0] + [ord(c) & 31 for c in hrp]
            mod = polymod(expanded + values + [0] * 6) ^ 1
            check = [(mod >> 5 * (5 - i)) & 31 for i in range(6)]
            return hrp + "1" + "".join(charset[v] for v in values + check)

        for values in ([0] * 10, [1] * 52, [31] * 51, [0] * 51 + [1], [0] * 53):   # tamanos distintos de 32 bytes o bits sobrantes
            with pytest.raises(InvalidKeyError):
                Keypair.from_nsec(encode("nsec", values))
        with pytest.raises(InvalidKeyError):
            Keypair.from_nsec(encode("npub", [0] * 52))


class TestSecretsAreNeverExposed:
    def setup_method(self):
        self.secret_hex = "b7e151628aed2a6abf7158809cf4f3c762e7160f38b4da56a784d9045190cfef"
        self.key = Keypair.from_hex(self.secret_hex)
        self.secret_bytes = bytes.fromhex(self.secret_hex)

    def test_repr_str_and_format_show_only_a_public_prefix(self):
        for text in (repr(self.key), str(self.key), f"{self.key}", f"{self.key!r}", "%s %r" % (self.key, self.key), format(self.key, ">40")):
            assert self.secret_hex not in text and self.secret_hex.upper() not in text
            assert self.key.public_hex not in text
            assert self.key.public_hex[:8] in text

    def test_there_is_no_public_attribute_with_the_secret(self):
        assert not hasattr(self.key, "__dict__")
        public = [n for n in dir(self.key) if not n.startswith("_")]
        assert sorted(public) == ["ecdh_x", "from_hex", "from_nsec", "from_secret_input", "generate", "public_hex", "sign"]

    def test_pickle_and_copy_are_blocked(self):
        for action in (lambda: pickle.dumps(self.key), lambda: copy.copy(self.key), lambda: copy.deepcopy(self.key)):
            with pytest.raises(TypeError):
                action()

    def test_errors_never_contain_the_input_or_the_secret(self):
        failures = []
        for call in (lambda: Keypair.from_hex(self.secret_hex + "0"), lambda: Keypair.from_nsec(self.secret_hex), lambda: Keypair(self.secret_bytes[:-1]),
                     lambda: self.key.sign(self.secret_bytes[:-1]), lambda: self.key.ecdh_x(self.secret_hex[:-1] + "g")):
            with pytest.raises((InvalidKeyError, SigningError)) as info:
                call()
            failures.append(str(info.value) + repr(info.value) + repr(info.value.args))
            assert info.value.__cause__ is None or info.type is not None
        joined = " ".join(failures)
        assert self.secret_hex not in joined and self.secret_hex[:-1] not in joined

    def test_equality_and_hash_use_only_the_public_key(self):
        same = Keypair.from_hex(self.secret_hex)
        assert same == self.key and hash(same) == hash(self.key) and self.key != Keypair.generate() and self.key != self.secret_hex


class TestPublicKeys:
    def test_known_good_and_bad_public_keys(self):
        assert is_valid_pubkey(PUB_1) and require_pubkey(PUB_1) == PUB_1
        for bad in ("", "0" * 64, PUB_1.upper(), PUB_1[:-1], PUB_1 + "0", "g" * 64, None, 5, b"x", "ff" * 32,
                    "5" + "0" * 63):   # 0 y valores sin punto en la curva
            assert not is_valid_pubkey(bad)
            with pytest.raises(InvalidKeyError):
                require_pubkey(bad)


class TestBip340:
    def test_sign_and_verify_roundtrip_with_fresh_randomness(self):
        key, message = Keypair.generate(), bytes(range(32))
        first, second = key.sign(message), key.sign(message)
        assert len(first) == 64 and verify_schnorr(key.public_hex, first, message) and verify_schnorr(key.public_hex, second, message)
        assert first != second  # aleatoriedad fresca en cada firma

    def test_verification_rejects_every_kind_of_tampering(self):
        key, message = Keypair.generate(), bytes(range(32))
        sig = key.sign(message)
        other = Keypair.generate()
        assert not verify_schnorr(other.public_hex, sig, message)
        assert not verify_schnorr(key.public_hex, sig, bytes(range(1, 33)))
        for i in (0, 31, 32, 63):
            mutated = bytearray(sig)
            mutated[i] ^= 1
            assert not verify_schnorr(key.public_hex, bytes(mutated), message)
        for bad_sig, bad_msg, bad_pub in ((sig[:-1], message, key.public_hex), (sig, message[:-1], key.public_hex), (sig, message, "0" * 64),
                                          (b"", message, key.public_hex), (sig, b"", key.public_hex), (sig, message, "zz")):
            assert not verify_schnorr(bad_pub, bad_sig, bad_msg)

    def test_a_library_error_during_verification_means_invalid_not_an_exception(self, monkeypatch):
        key, message = Keypair.generate(), bytes(32)
        sig = key.sign(message)

        def boom(self, signature, msg):
            raise ValueError("simulado")

        monkeypatch.setattr("app.nostr.keys.PublicKeyXOnly.verify", boom)
        assert verify_schnorr(key.public_hex, sig, message) is False

    def test_sign_requires_32_bytes(self):
        key = Keypair.generate()
        for bad in (b"", b"x" * 31, b"x" * 33, "x" * 32, None, bytearray(32)):
            with pytest.raises(SigningError):
                key.sign(bad)  # type: ignore[arg-type]


class TestEcdh:
    def test_shared_x_is_symmetric_and_unhashed(self):
        a, b = Keypair.from_hex(SECRET_1), Keypair.from_hex("0" * 63 + "2")
        assert a.ecdh_x(b.public_hex) == b.ecdh_x(a.public_hex) and len(a.ecdh_x(b.public_hex)) == 32
        # 1*2*G: coordenada X de 2G, sin hash (el ecdh de coincurve devolveria sha256 de la clave comprimida)
        assert a.ecdh_x(b.public_hex).hex() == "c6047f9441ed7d6d3045406e95c07cd85c778e4b8cef3ca7abac09b95c709ee5"

    @pytest.mark.parametrize("bad", ["", "0" * 64, "zz" * 32, "ff" * 32, PUB_1.upper(), None])
    def test_ecdh_rejects_invalid_peer_keys(self, bad):
        with pytest.raises(InvalidKeyError):
            Keypair.generate().ecdh_x(bad)  # type: ignore[arg-type]


OFFICIAL_CSV = FIXTURES_DIR / "bip340_official_test_vectors.csv"
OFFICIAL_CSV_SHA256 = "34c9d1d9c3a88d524bc80778540dc43f8306ec249a7485293063c376db851c2d"   # obtenido el 2026-11-21T00:55:30Z (ver fixtures/README.md)
COLUMNS = ["index", "secret key", "public key", "aux_rand", "message", "signature", "verification result", "comment"]


def _library_verify(pub: str, signature: bytes, message: bytes) -> bool:
    """Verificacion de la biblioteca (coincurve) sin las restricciones del producto: una clave publica invalida cuenta como FALSE."""
    from coincurve import PublicKeyXOnly
    try:
        return bool(PublicKeyXOnly(bytes.fromhex(pub)).verify(signature, message))
    except ValueError:
        return False


def run_bip340_csv(path: Path) -> dict[str, object]:
    """Ejecuta TODOS los vectores del CSV oficial de BIP-340. Un defecto de formato o un resultado distinto del esperado lanza AssertionError.

    Ningun vector se omite: cada fila produce un registro y el informe comprueba que `ejecutados == filas`. Rutas:
      * biblioteca (coincurve): verificacion de todas las filas; firma determinista con `aux_rand` cuando hay clave privada;
      * producto (`Keypair`, `verify_schnorr`): filas con mensaje de 32 bytes (los identificadores de eventos Nostr). Las filas con
        mensaje de otra longitud NO son admitidas por el producto ni por la firma de coincurve: se comprueba ese rechazo explicito.
    """
    from coincurve import PrivateKey
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        assert reader.fieldnames == COLUMNS, f"columnas inesperadas: {reader.fieldnames}"
        rows = list(reader)
    records: list[dict[str, object]] = []
    for row in rows:
        assert all(row[c] is not None for c in COLUMNS), f"fila incompleta: {row.get('index')}"
        assert row["verification result"] in ("TRUE", "FALSE"), f"resultado desconocido en la fila {row['index']}"
        expected = row["verification result"] == "TRUE"
        message, signature, pub = bytes.fromhex(row["message"]), bytes.fromhex(row["signature"]), row["public key"].lower()
        record: dict[str, object] = {"index": int(row["index"]), "expected": expected, "message_bytes": len(message)}
        assert _library_verify(pub, signature, message) == expected, f"coincurve discrepa en la fila {row['index']}"
        if row["secret key"]:
            secret, aux = bytes.fromhex(row["secret key"]), bytes.fromhex(row["aux_rand"])
            assert PrivateKey(secret).public_key_xonly.format().hex() == pub, f"clave publica derivada distinta en la fila {row['index']}"
            if len(message) == 32:
                assert PrivateKey(secret).sign_schnorr(message, aux) == signature, f"firma determinista distinta en la fila {row['index']}"
            else:
                with pytest.raises(ValueError):          # limitacion de la biblioteca, no modificada: solo firma mensajes de 32 bytes
                    PrivateKey(secret).sign_schnorr(message, aux)
        if len(message) == 32:
            assert verify_schnorr(pub, signature, message) == expected, f"el producto discrepa en la fila {row['index']}"
            if row["secret key"]:
                key = Keypair.from_hex(row["secret key"])
                assert key.public_hex == pub
                assert verify_schnorr(pub, key.sign(message), message)       # firma del producto (aleatoriedad fresca) con la clave oficial
            record["via"] = "producto+biblioteca"
        else:
            assert verify_schnorr(pub, signature, message) is False           # el producto solo verifica ids de 32 bytes (decision de diseno)
            if row["secret key"]:
                with pytest.raises(SigningError):
                    Keypair.from_hex(row["secret key"]).sign(message)
            record["via"] = "biblioteca (el producto lo rechaza por longitud)"
        records.append(record)
    assert len(records) == len(rows), "algun vector no se ejecuto"
    return {"filas": len(rows), "ejecutados": len(records), "omitidos": len(rows) - len(records), "positivos": sum(1 for r in records if r["expected"]),
            "negativos": sum(1 for r in records if not r["expected"]), "mensaje_distinto_de_32_bytes": sum(1 for r in records if r["message_bytes"] != 32),
            "registros": records}


class TestOfficialBip340Csv:
    def test_the_fixture_is_the_official_file_pinned_by_sha256(self):
        import hashlib
        assert hashlib.sha256(OFFICIAL_CSV.read_bytes()).hexdigest() == OFFICIAL_CSV_SHA256

    def test_all_official_vectors_run_and_none_is_skipped(self):
        report = run_bip340_csv(OFFICIAL_CSV)
        assert (report["filas"], report["ejecutados"], report["omitidos"]) == (19, 19, 0)
        assert (report["positivos"], report["negativos"], report["mensaje_distinto_de_32_bytes"]) == (9, 10, 4)
        assert sorted(r["index"] for r in report["registros"]) == list(range(19))   # type: ignore[attr-defined]

    def test_the_runner_fails_loudly_on_wrong_expectations_and_malformed_rows(self, tmp_path):
        lines = OFFICIAL_CSV.read_text(encoding="utf-8").splitlines()
        flipped = [lines[0]] + [lines[1].replace(",TRUE,", ",FALSE,")] + lines[2:]
        unknown = [lines[0]] + [lines[1].replace(",TRUE,", ",QUIZA,")] + lines[2:]
        short = [lines[0]] + [",".join(lines[1].split(",")[:5])] + lines[2:]
        bad_header = ["indice" + lines[0][5:]] + lines[1:]
        for name, content in (("flipped", flipped), ("unknown", unknown), ("short", short), ("header", bad_header)):
            path = tmp_path / f"{name}.csv"
            path.write_text(chr(10).join(content) + chr(10), encoding="utf-8")
            with pytest.raises((AssertionError, TypeError)):
                run_bip340_csv(path)
        assert run_bip340_csv(OFFICIAL_CSV)["omitidos"] == 0
