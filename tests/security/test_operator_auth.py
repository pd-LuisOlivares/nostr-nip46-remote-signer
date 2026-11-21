import logging
import time

import jwt
import pytest

from app.security.operator_auth import ALGORITHM, AUDIENCE, ISSUER, MAX_FAILURES, MAX_SESSIONS, REQUIRED_CLAIMS, AuthError, OperatorAuth, new_access_code

CODE = "k" * 32


def make(ttl: int = 60, **kw: object) -> OperatorAuth:
    return OperatorAuth(CODE, ttl_s=ttl, **kw)  # type: ignore[arg-type]


def forge(auth: OperatorAuth, *, key: bytes | None = None, algorithm: str = "HS256", drop: str | None = None, **over: object) -> str:
    now = int(time.time())
    session = auth.login(CODE)
    claims = jwt.decode(session.token, auth._key, algorithms=[ALGORITHM], audience=AUDIENCE, issuer=ISSUER)
    claims.update(over)
    if drop:
        claims.pop(drop)
    return jwt.encode(claims, key or auth._key, algorithm=algorithm) if now else ""


def test_login_issues_a_short_lived_hs256_token_with_all_claims() -> None:
    auth = make(ttl=60)
    issued = auth.login(CODE)
    assert jwt.get_unverified_header(issued.token)["alg"] == "HS256" and issued.expires_in_s == 60 and issued.csrf
    claims = jwt.decode(issued.token, auth._key, algorithms=["HS256"], audience=AUDIENCE, issuer=ISSUER)
    assert set(REQUIRED_CLAIMS) <= set(claims) and claims["exp"] - claims["iat"] == 60 and claims["sub"] == "operator" and claims["csrf"] == issued.csrf
    session = auth.verify(issued.token)
    assert session.csrf == issued.csrf and auth.remaining_s(session) in (59, 60) and auth.ttl_s == 60


def test_access_codes_and_keys_are_random_and_signing_key_changes_per_instance() -> None:
    assert len({new_access_code() for _ in range(20)}) == 20 and len(new_access_code()) >= 30
    a, b = make(), make()
    assert a._key != b._key and len(a._key) >= 32
    with pytest.raises(AuthError):
        b.verify(a.login(CODE).token)  # reiniciar (clave nueva) invalida los tokens anteriores


@pytest.mark.parametrize("code", ["", "x", CODE + " ", CODE.upper(), None, 5, b"k" * 32])
def test_wrong_codes_are_rejected(code: object) -> None:
    auth = make()
    with pytest.raises(AuthError):
        auth.login(code)
    assert auth.check_code(CODE) and not auth.check_code(code)


def test_constructor_refuses_weak_configuration() -> None:
    for code, ttl in (("short", 60), (CODE, 0), (CODE, -1)):
        with pytest.raises(ValueError):
            OperatorAuth(code, ttl_s=ttl)


@pytest.mark.parametrize("token", [None, 5, "", "x" * 19, "x" * 3000, "a.b.c", "Bearer abc", b"abc"])
def test_malformed_tokens_are_rejected(token: object) -> None:
    with pytest.raises(AuthError):
        make().verify(token)


def test_tampered_signature_wrong_key_and_alg_confusion_are_rejected() -> None:
    auth = make()
    good = auth.login(CODE).token
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
    first, second = auth.login(CODE), auth.login(CODE)
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
    tokens = [auth.login(CODE).token for _ in range(MAX_SESSIONS + 3)]
    assert len(auth._sessions) == MAX_SESSIONS
    assert auth.verify(tokens[-1])
    clock[0] += 31
    with pytest.raises(AuthError):
        auth.verify(tokens[-1])  # caducó para el servidor aunque PyJWT use el reloj real
    auth.login(CODE)
    assert len(auth._sessions) == 1  # las caducadas se purgan


def test_failure_rate_limit_and_window() -> None:
    mono = [0.0]
    auth = make(monotonic=lambda: mono[0])
    assert not auth.limited()
    for _ in range(MAX_FAILURES + 1):
        with pytest.raises(AuthError):
            auth.login("mal")
    assert auth.limited()
    mono[0] += 61
    assert not auth.limited()


def test_nothing_secret_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG):
        auth = make()
        token = auth.login(CODE).token
        auth.verify(token)
        with pytest.raises(AuthError):
            auth.login("incorrecto-1234567890")
    assert CODE not in caplog.text and token not in caplog.text and "incorrecto" not in caplog.text
