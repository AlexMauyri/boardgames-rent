"""Tests for app.auth.dpop: RFC 7638 thumbprint and JWK validation."""

import pytest

from app.auth.dpop import (
    InvalidJwkError,
    compute_jwk_thumbprint,
    parse_jwk_from_header,
)

_RFC7638_EC_JWK = {
    "kty": "EC",
    "crv": "P-256",
    "x": "MKBCTNIcKUSDii11ySs3526iDZ8AiTo7Tu6KPAqv7D4",
    "y": "4Etl6SRW2YiLUrN5vfvVHuhp7x8PxltmWWlbbM4IFyM",
    "use": "enc",
    "kid": "1",
}
_RFC7638_EC_THUMBPRINT = "cn-I_WNMClehiVp51i_0VpOENW1upEerA8sEam5hn-s"


# --- compute_jwk_thumbprint -------------------------------------------


def test_thumbprint_matches_rfc7638_vector():
    assert compute_jwk_thumbprint(_RFC7638_EC_JWK) == _RFC7638_EC_THUMBPRINT


def test_thumbprint_ignores_extra_members():
    bare = {k: _RFC7638_EC_JWK[k] for k in ("kty", "crv", "x", "y")}
    assert compute_jwk_thumbprint(bare) == _RFC7638_EC_THUMBPRINT

    noisy = {**bare, "kid": "different", "use": "sig", "alg": "ES256"}
    assert compute_jwk_thumbprint(noisy) == _RFC7638_EC_THUMBPRINT


def test_thumbprint_is_stable_regardless_of_dict_order():
    shuffled = {
        "y": _RFC7638_EC_JWK["y"],
        "x": _RFC7638_EC_JWK["x"],
        "crv": _RFC7638_EC_JWK["crv"],
        "kty": _RFC7638_EC_JWK["kty"],
    }
    assert compute_jwk_thumbprint(shuffled) == _RFC7638_EC_THUMBPRINT


def test_thumbprint_rejects_missing_member():
    without_x = {k: v for k, v in _RFC7638_EC_JWK.items() if k != "x"}
    with pytest.raises(InvalidJwkError):
        compute_jwk_thumbprint(without_x)


def test_thumbprint_rejects_non_string_member():
    broken = {**_RFC7638_EC_JWK, "x": 42}
    with pytest.raises(InvalidJwkError):
        compute_jwk_thumbprint(broken)


def test_thumbprint_rejects_empty_string_member():
    broken = {**_RFC7638_EC_JWK, "y": ""}
    with pytest.raises(InvalidJwkError):
        compute_jwk_thumbprint(broken)


# --- parse_jwk_from_header --------------------------------------------


def test_parse_jwk_returns_required_fields_only():
    parsed = parse_jwk_from_header(_RFC7638_EC_JWK)
    assert parsed == {
        "crv": "P-256",
        "kty": "EC",
        "x": _RFC7638_EC_JWK["x"],
        "y": _RFC7638_EC_JWK["y"],
    }
    assert "use" not in parsed
    assert "kid" not in parsed


def test_parse_jwk_rejects_non_dict():
    with pytest.raises(InvalidJwkError):
        parse_jwk_from_header("not-a-jwk")
    with pytest.raises(InvalidJwkError):
        parse_jwk_from_header(None)
    with pytest.raises(InvalidJwkError):
        parse_jwk_from_header(["kty", "EC"])


def test_parse_jwk_rejects_wrong_kty():
    rsa_like = {**_RFC7638_EC_JWK, "kty": "RSA"}
    with pytest.raises(InvalidJwkError):
        parse_jwk_from_header(rsa_like)


def test_parse_jwk_rejects_wrong_crv():
    p384 = {**_RFC7638_EC_JWK, "crv": "P-384"}
    with pytest.raises(InvalidJwkError):
        parse_jwk_from_header(p384)


def test_parse_jwk_rejects_private_member():
    with_d = {**_RFC7638_EC_JWK, "d": "some-private-scalar"}
    with pytest.raises(InvalidJwkError):
        parse_jwk_from_header(with_d)


def test_parse_jwk_rejects_missing_coordinate():
    without_y = {k: v for k, v in _RFC7638_EC_JWK.items() if k != "y"}
    with pytest.raises(InvalidJwkError):
        parse_jwk_from_header(without_y)


def test_parse_jwk_rejects_non_string_coordinate():
    broken = {**_RFC7638_EC_JWK, "x": 123}
    with pytest.raises(InvalidJwkError):
        parse_jwk_from_header(broken)


def test_parse_jwk_round_trips_through_thumbprint():
    parsed = parse_jwk_from_header(_RFC7638_EC_JWK)
    assert compute_jwk_thumbprint(parsed) == _RFC7638_EC_THUMBPRINT