import hashlib
import hmac

from code_review_agent.github.client import verify_webhook_signature


def test_verify_webhook_signature_valid():
    secret = "test-secret"
    payload = b'{"action":"opened"}'
    sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    assert verify_webhook_signature(payload, sig, secret)


def test_verify_webhook_signature_invalid():
    secret = "test-secret"
    payload = b'{"action":"opened"}'
    assert not verify_webhook_signature(payload, "sha256=bad", secret)
