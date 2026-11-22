"""Contraseña del administrador: política de longitud, Argon2id con los parámetros de producción, sal aleatoria y verificación sin filtrar la existencia."""
import logging

import pytest
from argon2 import Type

from app.security.passwords import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    PasswordPolicyError,
    PasswordService,
    default_hasher,
    validate_new_password,
)
from tests.support import PASSWORD, WRONG_PASSWORD, fast_passwords


# ------------------------------------------------------------------------------------------------ política
def test_a_reasonable_password_is_accepted_without_composition_rules() -> None:
    for ok in (PASSWORD, "abcdefghijkl", "frase larga solo con minusculas y espacios", "ñandú-ÁÉÍÓÚ-🙂-contraseña", "abcde" * 25):
        validate_new_password("operador", ok)  # sin exigir mayusculas, digitos ni simbolos


@pytest.mark.parametrize("password", ["", "corta", "x" * (MIN_PASSWORD_LENGTH - 1), "abcde" * 26, "con\x00nulo-incrustado", "con\nsalto-de-linea-1", "con\ttab-incrustado-1",
                                      "operador", "OPERADOR", "aaaaaaaaaaaaaaaa", "abababababababab", "1234123412341234"])
def test_invalid_passwords_are_rejected_with_a_rule_not_the_content(password: str) -> None:
    with pytest.raises(PasswordPolicyError) as info:
        validate_new_password("operador", password)
    assert password not in str(info.value) or password == ""


def test_a_password_equal_to_the_username_is_refused_even_when_long_enough() -> None:
    with pytest.raises(PasswordPolicyError, match="igual al nombre de usuario"):
        validate_new_password("administrador-local", "Administrador-Local")


def test_length_limits_are_exact() -> None:
    validate_new_password("u", "abcdefghijkl")  # 12
    validate_new_password("u", ("abcdefghij" * 13)[:MAX_PASSWORD_LENGTH])  # 128
    with pytest.raises(PasswordPolicyError):
        validate_new_password("u", "abcdefghijk")  # 11
    with pytest.raises(PasswordPolicyError):
        validate_new_password("u", ("abcdefghij" * 14)[: MAX_PASSWORD_LENGTH + 1])


# ------------------------------------------------------------------------------------------------ Argon2id
def test_production_hasher_is_argon2id_with_rfc9106_low_memory_parameters() -> None:
    hasher = default_hasher()
    assert (hasher.type, hasher.time_cost, hasher.memory_cost, hasher.parallelism, hasher.salt_len, hasher.hash_len) == (Type.ID, 3, 65536, 4, 16, 32)
    stored = PasswordService(hasher).hash(PASSWORD)
    assert stored.startswith("$argon2id$v=19$m=65536,t=3,p=4$") and PASSWORD not in stored and len(stored) < 512


def test_each_hash_uses_a_new_random_salt_and_verifies() -> None:
    service = fast_passwords()
    first, second = service.hash(PASSWORD), service.hash(PASSWORD)
    assert first != second and first.split("$")[4] != second.split("$")[4]  # sal distinta
    assert service.verify(first, PASSWORD) and service.verify(second, PASSWORD)
    assert not service.verify(first, WRONG_PASSWORD) and not service.verify(first, PASSWORD + " ") and not service.verify(first, "")


@pytest.mark.parametrize("stored", ["", "texto-plano", PASSWORD, "$argon2id$basura", "$2b$12$notargon", "$argon2id$v=19$m=8,t=1,p=1$AAAA$BBBB"])
def test_a_corrupt_or_foreign_hash_never_verifies_and_never_raises(stored: str) -> None:
    assert fast_passwords().verify(stored, PASSWORD) is False


def test_a_missing_account_does_a_full_verification_and_returns_false() -> None:
    service = fast_passwords()
    assert service.verify(None, PASSWORD) is False
    assert service._decoy is not None and service._decoy.startswith("$argon2id$")  # el señuelo se calculó (mismo costo que una cuenta real)
    assert service.verify(None, "") is False


def test_the_decoy_is_computed_lazily_and_reused() -> None:
    service = fast_passwords()
    assert service._decoy is None
    service.verify(None, "x")
    decoy = service._decoy
    service.verify(None, "y")
    assert service._decoy == decoy


def test_nothing_secret_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG):
        service = fast_passwords()
        stored = service.hash(PASSWORD)
        service.verify(stored, WRONG_PASSWORD)
        service.verify(None, WRONG_PASSWORD)
    assert PASSWORD not in caplog.text and WRONG_PASSWORD not in caplog.text and "$argon2" not in caplog.text
