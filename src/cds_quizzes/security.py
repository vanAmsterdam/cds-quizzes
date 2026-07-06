from __future__ import annotations

import hashlib


def normalize_sign_in_key(raw_key: str) -> str:
    return raw_key.strip().lower()


def hash_sign_in_key(raw_key: str) -> str:
    normalized = normalize_sign_in_key(raw_key)
    if not normalized:
        raise ValueError("Sign-in key cannot be blank.")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
