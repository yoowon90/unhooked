"""Encryption-at-rest for third-party financial tokens.

Plaid access tokens grant read (and with Transfer, money-movement) access to
a real bank login, so unlike the Gmail tokens they are never stored plaintext.
Symmetric Fernet encryption; the key lives in .env as TOKEN_ENCRYPTION_KEY
(generate one with `Fernet.generate_key()`). Losing the key just means users
re-link their bank — nothing is unrecoverable.
"""
import os

from cryptography.fernet import Fernet, InvalidToken


class CryptoError(RuntimeError):
    pass


def _fernet():
    key = os.getenv('TOKEN_ENCRYPTION_KEY')
    if not key:
        raise CryptoError('TOKEN_ENCRYPTION_KEY is not set in .env')
    return Fernet(key.encode())


def encrypt_token(plaintext):
    """str -> encrypted str safe to store in a DB text column."""
    if plaintext is None:
        return None
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext):
    """Inverse of encrypt_token. Raises CryptoError on a bad key/ciphertext."""
    if ciphertext is None:
        return None
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        raise CryptoError('Could not decrypt token — wrong TOKEN_ENCRYPTION_KEY?')
