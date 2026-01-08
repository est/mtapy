"""
Default crypto implementation using the `cryptography` library.

Provides ECDH P-256 key exchange and AES-CTR encryption for P2P credentials.
"""

import base64
from typing import Optional

from .interfaces import CryptoProvider, SessionCipher
from .constants import AES_IV


class DefaultSessionCipher(SessionCipher):
    """AES-CTR cipher for encrypting/decrypting P2P credentials."""

    def __init__(self, key: bytes):
        # BleSecurity.kt uses "TlsPremasterSecret" which returns the raw shared secret.
        # It then passes it to SecretKeySpec(..., "AES"). 
        # Since the secret is 32 bytes (P-256), this implies AES-256.
        self._key = key  # Full 32 bytes = AES-256
        self._iv = AES_IV # b"0102030405060708"

    def _get_cipher(self):
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        return Cipher(algorithms.AES(self._key), modes.CTR(self._iv))

    def encrypt(self, data: str) -> str:
        encryptor = self._get_cipher().encryptor()
        ct = encryptor.update(data.encode("utf-8")) + encryptor.finalize()
        return base64.b64encode(ct).decode("ascii")

    def decrypt(self, encoded_data: str) -> str:
        ct = base64.b64decode(encoded_data)
        decryptor = self._get_cipher().decryptor()
        pt = decryptor.update(ct) + decryptor.finalize()
        return pt.decode("utf-8")


class DefaultCryptoProvider(CryptoProvider):
    """
    Default crypto provider using the `cryptography` library.
    
    Uses ECDH with P-256 curve for key exchange and AES-CTR for encryption.
    """

    def __init__(self):
        """Generate a new EC P-256 keypair."""
        from cryptography.hazmat.primitives.asymmetric import ec
        
        self._private_key = ec.generate_private_key(ec.SECP256R1())
        self._public_key = self._private_key.public_key()

    def get_public_key(self) -> str:
        """Get base64-encoded X.509 SubjectPublicKeyInfo public key."""
        from cryptography.hazmat.primitives import serialization
        
        # Return X.509 encoded public key (SubjectPublicKeyInfo)
        der = self._public_key.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        return base64.b64encode(der).decode("ascii")

    def derive_session_cipher(self, peer_public_key_b64: str) -> SessionCipher:
        """
        Derive a session cipher from peer's public key using ECDH.
        
        Args:
            peer_public_key_b64: Base64-encoded X.509 SubjectPublicKeyInfo
            
        Returns:
            A DefaultSessionCipher for encrypting/decrypting P2P credentials.
        """
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        
        # Decode peer's public key
        peer_bytes = base64.b64decode(peer_public_key_b64)
        peer_key = serialization.load_der_public_key(peer_bytes)
        
        # Perform ECDH
        shared_secret = self._private_key.exchange(ec.ECDH(), peer_key)
        
        # BleSecurity.kt: KeyAgreement.getInstance("ECDH").doPhase(..., true).generateSecret("TlsPremasterSecret")
        # Returns the raw shared secret bytes.
        return DefaultSessionCipher(shared_secret)


def get_default_crypto_provider() -> CryptoProvider:
    """Get the default crypto provider."""
    return DefaultCryptoProvider()

