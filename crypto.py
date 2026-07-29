import os
import sys
from cryptography.fernet import Fernet


def generate_encryption_key() -> str:
    """Generate a URL-safe 32-byte base64-encoded Fernet key."""
    return Fernet.generate_key().decode("utf-8")


def get_fernet(key: str = None) -> Fernet:
    """Initialize Fernet instance using explicit key or CREDENTIALS_ENCRYPTION_KEY env var."""
    if key is None:
        key = os.getenv("CREDENTIALS_ENCRYPTION_KEY")
    if not key:
        raise ValueError(
            "CREDENTIALS_ENCRYPTION_KEY environment variable is not set. "
            "Generate one using `python crypto.py --generate-key`."
        )
    return Fernet(key.encode("utf-8") if isinstance(key, str) else key)


def encrypt_credential(plain_text: str, key: str = None) -> bytes:
    """Encrypt a plaintext string using Fernet and return encrypted bytes."""
    if plain_text is None:
        return None
    if isinstance(plain_text, bytes):
        plain_text = plain_text.decode("utf-8")
    if not plain_text:
        return b""
    f = get_fernet(key)
    return f.encrypt(plain_text.encode("utf-8"))


def decrypt_credential(cipher_bytes: bytes, key: str = None) -> str:
    """Decrypt Fernet encrypted bytes back to plaintext string."""
    if cipher_bytes is None:
        return None
    if not cipher_bytes:
        return ""
    if isinstance(cipher_bytes, str):
        cipher_bytes = cipher_bytes.encode("utf-8")
    f = get_fernet(key)
    return f.decrypt(cipher_bytes).decode("utf-8")


def mask_secret(secret: str, visible_chars: int = 4) -> str:
    """Mask sensitive string for logs/UI display (e.g. gsk_123456...7890 -> gsk_...7890)."""
    if not secret:
        return ""
    if len(secret) <= visible_chars * 2:
        return "*" * len(secret)
    prefix = "gsk_" if secret.startswith("gsk_") else ""
    suffix = secret[-visible_chars:]
    return f"{prefix}...{suffix}"


if __name__ == "__main__":
    if "--generate-key" in sys.argv:
        new_key = generate_encryption_key()
        print(f"Generated CREDENTIALS_ENCRYPTION_KEY:\n{new_key}")
    else:
        print("Usage: python crypto.py --generate-key")
