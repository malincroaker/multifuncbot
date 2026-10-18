import hashlib
import hmac
import json
from urllib.parse import urlencode

import pytest

from multifuncbot.core.web_auth import validate_init_data

TOKEN = "123:fake-test-token"


def signed_data(user_id=42, now=10000):
    fields = {"user": json.dumps({"id": user_id}), "auth_date": str(now), "query_id": "test"}
    check = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def test_valid_telegram_user_is_read_only_after_verification():
    assert validate_init_data(signed_data(), TOKEN, now=10000) == 42


@pytest.mark.parametrize(
    "raw,now",
    [
        (signed_data().replace("42", "43"), 10000),
        (signed_data(), 14000),
        (signed_data(), 9000),
        (signed_data(user_id="42"), 10000),
        (signed_data(user_id=True), 10000),
        (signed_data(user_id=-1), 10000),
        (signed_data() + "&auth_date=10000", 10000),
        ("hash=bad", 10000),
    ],
)
def test_tampered_expired_future_and_malformed_identity_is_rejected(raw, now):
    with pytest.raises(ValueError):
        validate_init_data(raw, TOKEN, now=now)
