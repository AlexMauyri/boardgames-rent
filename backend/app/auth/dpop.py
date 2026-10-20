"""DPoP helpers: JWK parsing and thumbprint computation."""

import base64
import hashlib
import json

ALLOWED_KTY = "EC"
ALLOWED_CRV = "P-256"

_REQUIRED_EC_FIELDS = ("crv", "kty", "x", "y")


class DpopError(Exception):
    """Base class for DPoP-related failures."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class InvalidJwkError(DpopError):
    """The ``jwk`` claim is malformed, missing members or disallowed."""


def _b64url(data: bytes) -> str:
    """Unpadded base64url encoding"""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def compute_jwk_thumbprint(jwk: dict) -> str:
    """Return the thumbprint of an EC P-256 JWK.

    Args:
        jwk: Public JWK. Extra members (``kid``, ``use``, ``alg``,
            ``key_ops``) are ignored.

    Returns:
        Base64url-encoded SHA-256 thumbprint.

    Raises:
        InvalidJwkError: A required member is missing or not a non-empty
            string.
    """
    for field in _REQUIRED_EC_FIELDS:
        value = jwk.get(field)
        if not isinstance(value, str) or not value:
            raise InvalidJwkError(f"missing or non-string JWK member: {field}")

    canonical = json.dumps(
        {field: jwk[field] for field in _REQUIRED_EC_FIELDS},
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical.encode("ascii")).digest()
    return _b64url(digest)


def parse_jwk_from_header(jwk: object) -> dict:
    """Validate the ``jwk`` claim from a DPoP proof's header.

    Args:
        jwk: The raw value from the proof header. Typed as ``object``
            because the header is untrusted JSON and may be anything.

    Returns:
        A dict with exactly ``kty``, ``crv``, ``x``, ``y`` (all strings).
        Extra members are stripped, so downstream code has nothing extra
        to worry about.

    Raises:
        InvalidJwkError: The value is not a dict, uses a wrong key type
            or curve, carries private key material, or is missing a
            required coordinate.
    """
    if not isinstance(jwk, dict):
        raise InvalidJwkError("jwk is not an object")

    kty = jwk.get("kty")
    if kty != ALLOWED_KTY:
        raise InvalidJwkError(f"unsupported kty: {kty!r}")

    crv = jwk.get("crv")
    if crv != ALLOWED_CRV:
        raise InvalidJwkError(f"unsupported crv: {crv!r}")

    if "d" in jwk:
        raise InvalidJwkError("jwk must not contain private key material")

    normalised: dict[str, str] = {}
    for field in _REQUIRED_EC_FIELDS:
        value = jwk.get(field)
        if not isinstance(value, str) or not value:
            raise InvalidJwkError(f"missing or non-string JWK member: {field}")
        normalised[field] = value
    return normalised
