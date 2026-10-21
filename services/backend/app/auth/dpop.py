"""DPoP helpers: JWK parsing and thumbprint computation."""
import base64
import hashlib
import json
import time

import jwt
import redis.asyncio as redis
from jwt.algorithms import ECAlgorithm

from app.auth.nonce import consume_nonce, issue_nonce

ALLOWED_KTY = "EC"
ALLOWED_CRV = "P-256"

_REQUIRED_EC_FIELDS = ("crv", "kty", "x", "y")

_PROOF_TYP = "dpop+jwt"
_PROOF_ALG = "ES256"

_JTI_KEY_PREFIX = "dpop:jti:"

DEFAULT_IAT_WINDOW_SECONDS = 60
DEFAULT_JTI_TTL_SECONDS = 300


class DpopError(Exception):
    """Base class for DPoP-related failures."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class InvalidJwkError(DpopError):
    """The ``jwk`` claim is malformed, missing members or disallowed."""


class DpopInvalidProof(DpopError):
    """The proof is malformed, has a bad signature, or a bad claim."""


class DpopExpired(DpopError):
    """The proof's ``iat`` is outside the accepted clock window."""


class DpopReplay(DpopError):
    """The proof's ``jti`` has already been seen."""


class DpopJktMismatch(DpopError):
    """The proof's key does not match the expected thumbprint."""


class DpopNonceRequired(DpopError):
    """The server requires a nonce in the proof; a fresh one is attached.

    Attributes:
        nonce: A freshly issued nonce value, ready for ``DPoP-Nonce``.
    """

    def __init__(self, nonce: str) -> None:
        self.nonce = nonce
        super().__init__("use_dpop_nonce")


def _b64url(data: bytes) -> str:
    """Unpadded base64url encoding"""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    """Decode a base64url string, tolerating missing padding."""
    pad = 4 - len(s) % 4
    if pad != 4:
        s += "=" * pad
    return base64.urlsafe_b64decode(s)


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


def _split_unverified(proof_jwt: str) -> tuple[dict, dict]:
    """Split a JWT into header and payload without verifying anything.

    Used for cheap structural checks before the expensive ECDSA verify.
    Everything returned by this function is untrusted; the caller must
    still verify the signature before acting on any claim.

    Args:
        proof_jwt: Compact serialised JWT.

    Returns:
        ``(header, payload)`` as plain dicts.

    Raises:
        DpopInvalidProof: The token is not a three-part JWT, or a part
            is not valid base64url-encoded JSON.
    """
    parts = proof_jwt.split(".")
    if len(parts) != 3:
        raise DpopInvalidProof("malformed_jwt")

    header_b64, payload_b64, _signature_b64 = parts
    try:
        header = json.loads(_b64url_decode(header_b64))
        payload = json.loads(_b64url_decode(payload_b64))
    except (ValueError, json.JSONDecodeError) as exc:
        raise DpopInvalidProof("malformed_jwt") from exc

    if not isinstance(header, dict) or not isinstance(payload, dict):
        raise DpopInvalidProof("malformed_jwt")

    return header, payload


def _verify_es256(proof_jwt: str, jwk: dict) -> dict:
    """Verify the ES256 signature using the public key from ``jwk``.

    Args:
        proof_jwt: Compact serialised JWT.
        jwk: Normalised JWK returned by ``parse_jwk_from_header``.

    Returns:
        The decoded payload (claims).

    Raises:
        DpopInvalidProof: The key is not usable, or the signature is
            invalid.
    """
    try:
        public_key = ECAlgorithm.from_jwk(json.dumps(jwk))
    except (ValueError, TypeError) as exc:
        raise DpopInvalidProof("invalid_jwk") from exc

    try:
        claims = jwt.decode(
            proof_jwt,
            key=public_key,
            algorithms=[_PROOF_ALG],
        )
    except jwt.InvalidTokenError as exc:
        raise DpopInvalidProof("signature") from exc

    return claims


async def verify_dpop_proof(
    proof_jwt: str,
    *,
    expected_htm: str,
    expected_htu: str,
    expected_jkt: str | None,
    redis_client: redis.Redis,
    require_nonce: bool = False,
    iat_window_seconds: int = DEFAULT_IAT_WINDOW_SECONDS,
    jti_ttl_seconds: int = DEFAULT_JTI_TTL_SECONDS,
) -> str:
    """Verify a DPoP proof and return its JWK thumbprint.

    Checks, in order (cheap first, expensive last):

    1. Structure: three-part JWT, base64url-encoded JSON.
    2. Header claims: ``typ == "dpop+jwt"``, ``alg == "ES256"``.
    3. ``jwk`` members: EC P-256, no private key.
    4. Thumbprint against ``expected_jkt`` (skipped if ``None``).
    5. ``htm`` matches the HTTP method.
    6. ``htu`` matches the request URI **without query and fragment**.
    7. ``iat`` inside ``[now - window, now + window]``.
    8. ``jti`` is a non-empty string.
    9. ES256 signature against the public key from ``jwk``.
    10. ``jti`` is fresh: ``SET dpop:jti:{jti} NX EX ttl``.

    The ``jti`` write happens **after** the signature check, so an
    attacker who replays a proof with a forged signature cannot burn the
    legitimate client's ``jti``.

    Args:
        proof_jwt: Compact serialised DPoP proof.
        expected_htm: HTTP method of the request being protected.
        expected_htu: Request URI without query string or fragment.
        expected_jkt: Expected JWK thumbprint. When ``None`` (login
            flow), the value computed from the proof is returned for the
            caller to bind into the new tokens. When set (refresh /
            logout), it is compared against the proof's thumbprint.
        redis_client: Redis client used for replay protection.
        require_nonce: When ``require_nonce`` is ``True``, 
            the proof must carry a ``nonce``
            claim whose value is present in Redis.
        iat_window_seconds: Accepted clock skew in either direction.
        jti_ttl_seconds: How long a used ``jti`` is remembered.

    Returns:
        The proof's JWK thumbprint (base64url string).

    Raises:
        DpopInvalidProof: Malformed token, wrong ``typ`` / ``alg``, bad
            signature, wrong ``htm`` / ``htu``, missing or non-string
            ``jti``, or invalid ``jwk``.
        DpopExpired: ``iat`` outside the accepted window.
        DpopReplay: ``jti`` already seen within the TTL.
        DpopJktMismatch: ``expected_jkt`` was given and does not match.
        InvalidJwkError: The JWK in the header is unusable.
    """
    header, payload = _split_unverified(proof_jwt)

    if header.get("typ") != _PROOF_TYP:
        raise DpopInvalidProof("typ")
    if header.get("alg") != _PROOF_ALG:
        raise DpopInvalidProof("alg")

    jwk = parse_jwk_from_header(header.get("jwk"))
    thumbprint = compute_jwk_thumbprint(jwk)

    if expected_jkt is not None and thumbprint != expected_jkt:
        raise DpopJktMismatch("jkt")

    htm = payload.get("htm")
    if htm != expected_htm:
        raise DpopInvalidProof("htm")

    htu = payload.get("htu")
    if htu != expected_htu:
        raise DpopInvalidProof("htu")

    iat = payload.get("iat")
    if not isinstance(iat, int):
        raise DpopInvalidProof("iat")
    now = int(time.time())
    if abs(now - iat) > iat_window_seconds:
        raise DpopExpired("iat")

    jti = payload.get("jti")
    if not isinstance(jti, str) or not jti:
        raise DpopInvalidProof("jti")

    claims = _verify_es256(proof_jwt, jwk)

    if claims.get("jti") != jti:
        raise DpopInvalidProof("jti")

    if require_nonce:
        proof_nonce = claims.get("nonce")
        if not isinstance(proof_nonce, str) or not proof_nonce:
            fresh = await issue_nonce(redis_client)
            raise DpopNonceRequired(fresh)
        if not await consume_nonce(redis_client, proof_nonce):
            fresh = await issue_nonce(redis_client)
            raise DpopNonceRequired(fresh)

    stored = await redis_client.set(
        f"{_JTI_KEY_PREFIX}{jti}",
        "1",
        nx=True,
        ex=jti_ttl_seconds,
    )
    if not stored:
        raise DpopReplay("jti")

    return thumbprint