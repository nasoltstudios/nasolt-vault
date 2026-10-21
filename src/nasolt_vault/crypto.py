"""
crypto.py — Cryptographic primitives for Nasolt Vault.

Key derivation : Argon2id
Encryption      : AES-256-GCM (AEAD)
NO NETWORK      : this module imports nothing that touches the network.
"""

from __future__ import annotations

import os
import hashlib
from typing import Tuple

from argon2.low_level import hash_secret_raw, Type

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MAGIC: bytes = b"NSLT"          # file magic to detect a valid vault file
FILE_VERSION: int = 1

SALT_SIZE: int = 32             # Argon2 salt  (256 bits)
NONCE_SIZE: int = 12            # AES-GCM nonce (96 bits)
TAG_SIZE: int = 16              # AES-GCM auth tag (128 bits)
KEY_SIZE: int = 32              # AES-256 key

# Argon2id parameters (balanced for a desktop app — secure but not sluggish)
ARGON2_TIME_COST: int = 3
ARGON2_MEMORY_COST: int = 65536   # 64 MB
ARGON2_PARALLELISM: int = 4
ARGON2_HASH_LEN: int = 32         # output = 256 bits → AES-256 key


# ---------------------------------------------------------------------------
# Key Derivation (Argon2id)
# ---------------------------------------------------------------------------
def derive_key(master_password: str, salt: bytes) -> bytes:
    """
    Derive a 256-bit AES key from *master_password* and *salt* using Argon2id.

    The salt must be the per-vault random salt (stored in the vault file header).
    """
    return hash_secret_raw(
        secret=master_password.encode("utf-8"),
        salt=salt,
        time_cost=ARGON2_TIME_COST,
        memory_cost=ARGON2_MEMORY_COST,
        parallelism=ARGON2_PARALLELISM,
        hash_len=ARGON2_HASH_LEN,
        type=Type.ID,
    )


# ---------------------------------------------------------------------------
# AES-256-GCM Encryption / Decryption
# ---------------------------------------------------------------------------
def encrypt_aes_gcm(plaintext: bytes, key: bytes) -> Tuple[bytes, bytes, bytes]:
    """
    Encrypt *plaintext* with AES-256-GCM.

    Returns (nonce, tag, ciphertext).
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    aesgcm = AESGCM(key)
    nonce = os.urandom(NONCE_SIZE)
    # AESGCM.encrypt appends the 16-byte tag to the ciphertext, so we split it.
    ct_with_tag = aesgcm.encrypt(nonce, plaintext, associated_data=None)
    ciphertext = ct_with_tag[:-TAG_SIZE]
    tag = ct_with_tag[-TAG_SIZE:]
    return nonce, tag, ciphertext


def decrypt_aes_gcm(nonce: bytes, tag: bytes, ciphertext: bytes, key: bytes) -> bytes:
    """
    Decrypt *ciphertext* authenticated with *tag* under AES-256-GCM.
    Raises cryptography.exceptions.InvalidTag if the key or data is wrong.
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.exceptions import InvalidTag

    aesgcm = AESGCM(key)
    try:
        return aesgcm.decrypt(nonce, ciphertext + tag, associated_data=None)
    except InvalidTag:
        raise ValueError("Decryption failed — wrong master password or corrupted file.")


# ---------------------------------------------------------------------------
# Vault file format helpers
# ---------------------------------------------------------------------------
VAULT_FILE_HEADER_LEN: int = (
    len(MAGIC) + 1 + SALT_SIZE + NONCE_SIZE + TAG_SIZE
)  # 4 + 1 + 32 + 12 + 16 = 65 bytes


def read_vault_header(raw: bytes) -> dict:
    """Parse the binary vault file header into a dict."""
    if len(raw) < VAULT_FILE_HEADER_LEN:
        raise ValueError("Vault file is too small to be valid.")
    if raw[: len(MAGIC)] != MAGIC:
        raise ValueError("Not a Nasolt Vault file (bad magic).")
    if raw[len(MAGIC)] != FILE_VERSION:
        raise ValueError(f"Unsupported vault file version: {raw[len(MAGIC)]}")

    offset = len(MAGIC) + 1
    salt = raw[offset : offset + SALT_SIZE]
    offset += SALT_SIZE
    nonce = raw[offset : offset + NONCE_SIZE]
    offset += NONCE_SIZE
    tag = raw[offset : offset + TAG_SIZE]
    ciphertext = raw[offset + TAG_SIZE :]
    return {
        "salt": salt,
        "nonce": nonce,
        "tag": tag,
        "ciphertext": ciphertext,
    }


def build_vault_blob(salt: bytes, nonce: bytes, tag: bytes, ciphertext: bytes) -> bytes:
    """Pack header + ciphertext into the on-disk vault blob."""
    return MAGIC + bytes([FILE_VERSION]) + salt + nonce + tag + ciphertext


# ---------------------------------------------------------------------------
# Memory-safe password hashing fallback (for password-strength display only)
# ---------------------------------------------------------------------------
def sha256_hex(data: bytes) -> str:
    """Return hex digest — used only for non-security UI indicators."""
    return hashlib.sha256(data).hexdigest()
