"""Sesión JWT del operador (sin FastAPI): emisión, verificación estricta, revocación y los dos límites de fallos independientes."""
import logging
import time

import jwt
import pytest

from app.security.operator_auth import (
    ALGORITHM,
    AUDIENCE,
    ISSUER,
    LOGIN_WINDOW_S,
    MAX_LOGIN_FAILURES,
    MAX_SESSIONS,
    MAX_TOKEN_FAILURES,
    REQUIRED_CLAIMS,
    TOKEN_WINDOW_S,
    AuthError,
    OperatorAuth,
)


def make(ttl: int = 60, **kw: object) -> OperatorAuth:
    return OperatorAuth(ttl_s=ttl, **kw)  # type: ignore[arg-type]


def forge(auth: OperatorAuth, *, key: bytes | None = None, algorithm: str = "HS256", drop: str | None = None, **over: object) -> str:
    issued = auth.issue()
    claims = jwt.decode(issued.token, auth._key, algorithms=[ALGORITHM], audience=AUDIENCE, issuer=ISSUER)
    claims.update(over)
    if drop:
        claims.pop(drop)
    return jwt.encode(claims, key or auth._key, algorithm=algorithm)


def test_issue_creates_a_short_lived_hs256_token_with_all_claims() -> None:
    auth = make(ttl=60)
    issued = auth.issue()
    assert jwt.get_unverified_header(issued.token)["alg"] == "HS256" and issued.expires_in_s == 60 and issued.csrf and issued.jti
    claims = jwt.decode(issued.token, auth._key, algorithms=["HS256"], audience=AUDIENCE, issuer=ISSUER)
    assert set(REQUIRED_CLAIMS) <= set(claims) and claims["exp"] - claims["iat"] == 60 and claims["sub"] == "operator" and claims["csrf"] == issued.csrf
    assert claims["jti"] == issued.jti
    session = auth.verify(issued.token)
    assert session.csrf == issued.csrf and auth.remaining_s(session) in (59, 60) and auth.ttl_s == 60


def test_signing_key_is_random_per_instance_and_restart_invalidates_tokens() -> None:
    a, b = make(), make()
    assert a._key != b._key and len(a._key) >= 32
    with pytest.raises(AuthError):
        b.verify(a.issue().token)  # reiniciar (clave nueva) invalida los tokens anteriores


def test_constructor_refuses_a_non_positive_ttl() -> None:
    for ttl in (0, -1):
        with pytest.raises(ValueError):
            OperatorAuth(ttl_s=ttl)


@pytest.mark.parametrize("token", [None, 5, "", "x" * 19, "x" * 3000, "a.b.c", "Bearer abc", b"abc"])
def test_malformed_tokens_are_rejected(token: object) -> None:
    with pytest.raises(AuthError):
        make().verify(token)


def test_tampered_signature_wrong_key_and_alg_confusion_are_rejected() -> None:
    auth = make()
    good = auth.issue().token
    head, body, sig = good.split(".")
    for bad in (f"{head}.{body}.{sig[:-3]}AAA", f"{head}.{body}x.{sig}", f"{head}.{body}."):
        with pytest.raises(AuthError):
            auth.verify(bad)
    with pytest.raises(AuthError):
        auth.verify(forge(auth, key=b"z" * 48))  # firmado con otra clave
    with pytest.raises(AuthError):
        auth.verify(forge(auth, algorithm="HS384"))  # algoritmo no permitido aunque la clave sea la correcta
    none_token = jwt.encode({"sub": "operator"}, key="", algorithm="none")
    with pytest.raises(AuthError):
        auth.verify(none_token)


def test_expired_and_not_yet_valid_tokens_are_rejected() -> None:
    auth = make()
    now = int(time.time())
    for over in ({"exp": now - 5}, {"nbf": now + 3600}, {"iat": now + 3600}):
        with pytest.raises(AuthError):
            auth.verify(forge(auth, **over))


@pytest.mark.parametrize("claim", REQUIRED_CLAIMS)
def test_every_required_claim_is_enforced(claim: str) -> None:
    auth = make()
    with pytest.raises(AuthError):
        auth.verify(forge(auth, drop=claim))


@pytest.mark.parametrize("over", [{"iss": "otro"}, {"aud": "otro"}, {"sub": "admin"}, {"jti": "desconocido"}, {"csrf": "otro"}, {"jti": 5}, {"csrf": 5}])
def test_wrong_claim_values_are_rejected(over: dict[str, object]) -> None:
    auth = make()
    with pytest.raises(AuthError):
        auth.verify(forge(auth, **over))


def test_logout_revocation_and_revoke_all() -> None:
    auth = make()
    first, second = auth.issue(), auth.issue()
    session = auth.verify(first.token)
    auth.revoke(session.jti)
    with pytest.raises(AuthError):
        auth.verify(first.token)
    assert auth.verify(second.token)
    auth.revoke_all()
    with pytest.raises(AuthError):
        auth.verify(second.token)


def test_logical_expiry_uses_the_injected_clock_and_sessions_are_capped() -> None:
    clock = [float(int(time.time()))]
    auth = make(ttl=30, now=lambda: clock[0])
    tokens = [auth.issue().token for _ in range(MAX_SESSIONS + 3)]
    assert len(auth._sessions) == MAX_SESSIONS
    assert auth.verify(tokens[-1])
    clock[0] += 31
    with pytest.raises(AuthError):
        auth.verify(tokens[-1])  # caducó para el servidor aunque PyJWT use el reloj real
    auth.issue()
    assert len(auth._sessions) == 1  # las caducadas se purgan


# ------------------------------------------------------------------------------------------------ límites de fallos (P-35)
def test_login_attempts_are_counted_when_reserved_and_forgiven_only_on_success() -> None:
    mono = [0.0]
    auth = make(monotonic=lambda: mono[0])
    assert not auth.login_limited()
    stamps = [auth.reserve_login_attempt() for _ in range(MAX_LOGIN_FAILURES - 1)]
    assert not auth.login_limited()
    last = auth.reserve_login_attempt()
    assert auth.login_limited()  # el intento en vuelo cuenta: una rafaga simultanea no puede pasar del limite
    auth.release_login_attempt(last)  # exito: se descuenta
    assert not auth.login_limited()
    assert len(stamps) == MAX_LOGIN_FAILURES - 1


def test_login_window_expires_and_retry_after_is_bounded() -> None:
    mono = [0.0]
    auth = make(monotonic=lambda: mono[0])
    for _ in range(MAX_LOGIN_FAILURES):
        auth.reserve_login_attempt()
    assert auth.login_limited() and auth.login_retry_after_s() == int(LOGIN_WINDOW_S)
    mono[0] += 100
    assert auth.login_limited() and 199 <= auth.login_retry_after_s() <= 201
    mono[0] += LOGIN_WINDOW_S
    assert not auth.login_limited() and auth.login_retry_after_s() == 1


def test_releasing_an_unknown_or_expired_attempt_is_harmless() -> None:
    auth = make()
    auth.release_login_attempt(123.456)
    assert not auth.login_limited()


def test_token_failures_are_a_separate_counter_from_login_attempts() -> None:
    mono = [0.0]
    auth = make(monotonic=lambda: mono[0])
    for _ in range(MAX_TOKEN_FAILURES):
        with pytest.raises(AuthError):
            auth.verify("x" * 30)
    assert auth.token_limited() and not auth.login_limited()  # los tokens invalidos NO bloquean el inicio de sesion
    for _ in range(MAX_LOGIN_FAILURES):
        auth.reserve_login_attempt()
    assert auth.login_limited()
    mono[0] += TOKEN_WINDOW_S + 1
    assert not auth.token_limited() and auth.login_limited()  # ventanas distintas


def test_a_valid_token_is_never_counted_as_a_failure() -> None:
    auth = make()
    token = auth.issue().token
    for _ in range(MAX_TOKEN_FAILURES * 3):
        auth.verify(token)
    assert not auth.token_limited()


def test_nothing_secret_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG):
        auth = make()
        token = auth.issue().token
        auth.verify(token)
        with pytest.raises(AuthError):
            auth.verify("incorrecto-1234567890")
    assert token not in caplog.text and "incorrecto" not in caplog.text
