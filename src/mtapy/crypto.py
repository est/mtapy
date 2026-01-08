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

    def __init__(self, candidates: list[tuple[bytes, bytes]]):
        self._candidates = candidates

    def _get_cipher(self, key, iv):
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        return Cipher(algorithms.AES(key), modes.CTR(iv))

    def encrypt(self, data: str) -> str:
        # Encryption uses the first candidate
        key, iv = self._candidates[0]
        encryptor = self._get_cipher(key, iv).encryptor()
        ct = encryptor.update(data.encode("utf-8")) + encryptor.finalize()
        return base64.b64encode(ct).decode("ascii")

    def decrypt(self, encoded_data: str) -> str:
        # Debug: Print incoming base64 length
        print(f"DEBUG: Decrypting {len(encoded_data)} chars of Base64...")
        
        try:
            ct = base64.b64decode(encoded_data)
        except Exception as e:
            print(f"DEBUG: Base64 decode failed: {e}")
            raise

        last_error = None
        for i, (key, iv) in enumerate(self._candidates):
            try:
                decryptor = self._get_cipher(key, iv).decryptor()
                pt = decryptor.update(ct) + decryptor.finalize()
                
                # LOGGING PLAINTEXT IS CRITICAL
                # print(f"DEBUG: Attempt {i} | PT: {pt.hex()} | {list(pt)}")
                
                # If this succeeds, we found the right combo!
                text = pt.decode("utf-8")
                print(f"DEBUG: SUCCESS with candidate {i} | PT: {pt.hex()} -> '{text}'")
                return text
            except UnicodeDecodeError as e:
                last_error = e
                continue
            except Exception as e:
                # print(f"DEBUG: Crypto Error {i}: {e}")
                last_error = e
                continue
        
        # If we get here, nothing worked, but we print the last attempt's hex for debug
        # print("DEBUG: All attempts failed.")
        if last_error:
            raise last_error
        raise ValueError("Decryption failed")


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
        
        # Prepare key candidates for "Smart Decrypt"
        import hashlib
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
        from cryptography.hazmat.primitives import hashes
        
        # HKDF Helper: derive 32 bytes (Key + IV)
        def get_hkdf_pair(info: bytes) -> tuple[bytes, bytes]:
            mk = HKDF(
                algorithm=hashes.SHA256(),
                length=32,
                salt=None,
                info=info,
            ).derive(shared_secret)
            return (mk[:16], mk[16:])

        # Fixed IV Constants
        IV_MAIN = AES_IV
        IV_SEQ = bytes(range(1, 17))
        IV_NULL = b'\x00' * 16

        # Candidate Keys
        raw_key = shared_secret[:16]
        sha_digest = hashlib.sha256(shared_secret).digest()
        sha_key = sha_digest[:16]
        sha_iv = sha_digest[16:]

        candidates = [
            # 1. Raw Key + Fixed IVs
            (raw_key, IV_MAIN),
            (raw_key, IV_SEQ),
            (raw_key, IV_NULL),
            
            # 2. SHA Key + Fixed IVs
            (sha_key, IV_MAIN),
            (sha_key, IV_SEQ),
            (sha_key, IV_NULL),

            # 3. SHA Key + SHA IV (Strong candidate for no-IV-exchange protocols)
            (sha_key, sha_iv),

            # 4. HKDF (Key+IV)
            get_hkdf_pair(b"Google Nearby SharingP2P Key"),
            get_hkdf_pair(b"Google Nearby Sharing P2P Key"),
            get_hkdf_pair(b"MTA P2P Key"),
        ]
        
        return DefaultSessionCipher(candidates)


def get_default_crypto_provider() -> CryptoProvider:
    """Get the default crypto provider."""
    return DefaultCryptoProvider()
