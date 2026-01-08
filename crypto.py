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
        """
        Initialize with a 16-byte AES key.
        
        Args:
            key: AES key (first 16 bytes of ECDH shared secret)
        """
        # Import here to make cryptography optional
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        
        self._key = key[:16]  # Use first 16 bytes for AES-128
        self._iv = AES_IV

    def _get_cipher(self):
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        return Cipher(algorithms.AES(self._key), modes.CTR(self._iv))

    def encrypt(self, data: str) -> str:
        """Encrypt a string, return base64-encoded ciphertext."""
        encryptor = self._get_cipher().encryptor()
        ct = encryptor.update(data.encode("utf-8")) + encryptor.finalize()
        return base64.b64encode(ct).decode("ascii")

    def decrypt(self, encoded_data: str) -> str:
        """Decrypt base64-encoded ciphertext, return plaintext."""
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
        
        der = self._public_key.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return base64.b64encode(der).decode("ascii")

    def derive_session_cipher(self, peer_public_key: str) -> SessionCipher:
        """
        Derive a session cipher from peer's public key using ECDH.
        
        Args:
            peer_public_key: Base64-encoded X.509 SubjectPublicKeyInfo
            
        Returns:
            A DefaultSessionCipher for encrypting/decrypting P2P credentials.
        """
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
        from cryptography.hazmat.primitives import hashes
        
        # Decode peer's public key
        peer_key_der = base64.b64decode(peer_public_key)
        peer_key = serialization.load_der_public_key(peer_key_der)
        
        # Perform ECDH
        shared_secret = self._private_key.exchange(ec.ECDH(), peer_key)
        
        # The original Java code uses "TlsPremasterSecret" algorithm which
        # returns the raw shared secret. We do the same here.
        # Use first 16 bytes as AES key.
        return DefaultSessionCipher(shared_secret)


def get_default_crypto_provider() -> CryptoProvider:
    """Get the default crypto provider."""
    return DefaultCryptoProvider()
