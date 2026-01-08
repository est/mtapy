"""Tests for crypto module."""

import pytest


def test_crypto_import():
    """Test that crypto module can be imported."""
    from mtapy.crypto import DefaultCryptoProvider, DefaultSessionCipher


def test_public_key_generation():
    """Test public key generation."""
    pytest.importorskip("cryptography")
    from mtapy.crypto import DefaultCryptoProvider
    
    provider = DefaultCryptoProvider()
    public_key = provider.get_public_key()
    
    # Public key should be base64 encoded
    assert isinstance(public_key, str)
    assert len(public_key) > 50  # EC P-256 public key is ~91 chars base64


def test_ecdh_key_exchange():
    """Test ECDH key exchange between two parties."""
    pytest.importorskip("cryptography")
    from mtapy.crypto import DefaultCryptoProvider
    
    # Create two providers (simulating sender and receiver)
    alice = DefaultCryptoProvider()
    bob = DefaultCryptoProvider()
    
    # Exchange public keys and derive session ciphers
    alice_cipher = alice.derive_session_cipher(bob.get_public_key())
    bob_cipher = bob.derive_session_cipher(alice.get_public_key())
    
    # Test encryption/decryption
    plaintext = "DIRECT-ABCD1234"
    
    # Alice encrypts, Bob decrypts
    ciphertext = alice_cipher.encrypt(plaintext)
    decrypted = bob_cipher.decrypt(ciphertext)
    
    assert decrypted == plaintext


def test_session_cipher_encrypt_decrypt():
    """Test session cipher encrypt/decrypt roundtrip."""
    pytest.importorskip("cryptography")
    from mtapy.crypto import DefaultCryptoProvider
    
    alice = DefaultCryptoProvider()
    bob = DefaultCryptoProvider()
    
    cipher = alice.derive_session_cipher(bob.get_public_key())
    
    test_cases = [
        "DIRECT-TEST1234",
        "password123!@#",
        "aa:bb:cc:dd:ee:ff",
        "こんにちは",  # Unicode
    ]
    
    for plaintext in test_cases:
        encrypted = cipher.encrypt(plaintext)
        # Encrypted should be base64
        assert encrypted != plaintext
        
        # Decrypt with same cipher should work
        decrypted = cipher.decrypt(encrypted)
        assert decrypted == plaintext
