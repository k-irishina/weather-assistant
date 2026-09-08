"""Print a fresh VAPID keypair for the `web.vapid` section of config.yml.
Needed to enable push for devices via web
"""
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def b64url(raw: bytes) -> str:
    """base64url with the padding stripped, which is what VAPID expects."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def generate() -> tuple[str, str]:
    key = ec.generate_private_key(ec.SECP256R1())
    private = b64url(key.private_numbers().private_value.to_bytes(32, "big"))
    public = b64url(
        key.public_key().public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint,
        )
    )
    return public, private


if __name__ == "__main__":
    public, private = generate()
    print("Copy these into the web.vapid section of config.yml:\n")
    print(f"    public-key: '{public}'")
    print(f"    private-key: '{private}'")
