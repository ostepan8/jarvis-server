import os
from server.crypto import encrypt, decrypt


def test_encrypt_decrypt_roundtrip():
    os.environ['CONFIG_SECRET'] = os.environ.get('CONFIG_SECRET', 'a'*44)
    secret = 'secret-value'
    enc = encrypt(secret)
    assert enc != secret
    dec = decrypt(enc)
    assert dec == secret
