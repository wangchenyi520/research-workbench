import sys

import pytest

from app.services import secure


@pytest.mark.skipif(sys.platform != "win32", reason="Windows DPAPI is Windows-only")
def test_encrypt_decrypt_roundtrip():
    token = secure.encrypt_str("local-secret-value")
    assert token.startswith("enc:")
    assert secure.decrypt_str(token) == "local-secret-value"


def test_plain_values_are_preserved():
    assert secure.decrypt_str("plain") == "plain"
    assert secure.decrypt_str("") == ""
