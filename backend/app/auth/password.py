"""Argon2id password hashing."""

import secrets

from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error

_HASHER = PasswordHasher(
    time_cost=2,
    memory_cost=19456,
    parallelism=1,
    hash_len=32,
    salt_len=16,
)

DUMMY_HASH: str = _HASHER.hash(secrets.token_hex(32))


def hash_password(plain: str) -> str:
    """Hash a plaintext password with argon2id.

    Args:
        plain: The plaintext password. Arbitrary length and arbitrary
            Unicode; argon2 has no input truncation limit, so Cyrillic
            passwords of any length hash correctly and completely.

    Returns:
        The argon2id digest, including its embedded salt and parameters.
    """
    return _HASHER.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Check a plaintext password against a stored digest.

    Args:
        plain: The plaintext password to check.
        hashed: A stored argon2 digest, or arbitrary junk.

    Returns:
        True if the password matches the digest, False otherwise.
    """
    try:
        return _HASHER.verify(hashed, plain)
    except Argon2Error:
        return False