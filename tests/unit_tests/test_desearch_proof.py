"""Unit tests for Desearch proof verification (shared.desearch_proof)."""
import sys
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from shared.desearch_proof import verify_proof


def test_verify_proof_expired_returns_false():
    """Expired proof should return False before any Keypair use."""
    expiry_past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    result = verify_proof(
        coldkey="5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutgY",
        response_body=b"{}",
        signature_hex="00" * 64,
        timestamp=expiry_past,
        expiry=expiry_past,
    )
    assert result is False


def test_verify_proof_invalid_signature_hex_returns_false():
    """Invalid hex signature should return False."""
    future = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    result = verify_proof(
        coldkey="5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutgY",
        response_body=b"{}",
        signature_hex="not-hex",
        timestamp=future,
        expiry=future,
    )
    assert result is False


def test_verify_proof_malformed_expiry_returns_false():
    """Malformed expiry should return False."""
    result = verify_proof(
        coldkey="5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutgY",
        response_body=b"{}",
        signature_hex="00" * 64,
        timestamp="2024-01-01T00:00:00+00:00",
        expiry="not-a-date",
    )
    assert result is False


def test_verify_proof_valid_calls_keypair_verify():
    """Valid proof should call Keypair.verify and return True (when bittensor available)."""
    pytest = __import__("pytest")
    pytest.importorskip("bittensor")
    # Ensure bittensor has Keypair so patch() works even if another test replaced bittensor with MockBt
    bt = sys.modules.get("bittensor")
    if bt is not None and not hasattr(bt, "Keypair"):
        bt.Keypair = MagicMock()
    with patch("bittensor.Keypair") as mock_keypair_cls:
        mock_keypair_cls.return_value.verify.return_value = True
        future = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        result = verify_proof(
            coldkey="5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutgY",
            response_body=b'{"results":[]}',
            signature_hex="00" * 64,
            timestamp=future,
            expiry=future,
        )
        assert result is True
        mock_keypair_cls.return_value.verify.assert_called_once()
        msg = mock_keypair_cls.return_value.verify.call_args[0][0]
        sig = mock_keypair_cls.return_value.verify.call_args[0][1]
        assert b"|" in msg
        assert len(sig) == 64


def test_verify_proof_verify_returns_false():
    """When Keypair.verify returns False, verify_proof returns False (when bittensor available)."""
    pytest = __import__("pytest")
    pytest.importorskip("bittensor")
    bt = sys.modules.get("bittensor")
    if bt is not None and not hasattr(bt, "Keypair"):
        bt.Keypair = MagicMock()
    with patch("bittensor.Keypair") as mock_keypair_cls:
        mock_keypair_cls.return_value.verify.return_value = False
        future = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        result = verify_proof(
            coldkey="5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutgY",
            response_body=b"{}",
            signature_hex="00" * 64,
            timestamp=future,
            expiry=future,
        )
        assert result is False
