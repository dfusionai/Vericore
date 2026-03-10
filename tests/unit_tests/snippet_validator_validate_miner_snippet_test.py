"""
Unit tests for validate_miner_snippet refactor: dispatch (web vs desearch) and
response shape parity for normal (web) searches.

Requires bittensor (and project deps); use pytest.importorskip so collection
is skipped when not installed.
"""
import pytest

pytest.importorskip("bittensor")

from unittest.mock import AsyncMock, patch

from shared.veridex_protocol import (
    SourceEvidence,
    SourceType,
    VericoreStatementResponse,
)
from validator.snippet_validator import SnippetValidator


@pytest.fixture
def validator():
    return SnippetValidator()


@pytest.fixture
def web_evidence():
    """Normal web source evidence (HTTPS)."""
    return SourceEvidence(
        url="https://example.com/page",
        excerpt="Some excerpt from the page.",
        source_type=SourceType.WEB.value,
    )


@pytest.fixture
def desearch_evidence():
    """Desearch source evidence."""
    return SourceEvidence(
        url="https://example.com/page",
        excerpt="Desearch excerpt.",
        source_type=SourceType.DESEARCH.value,
    )


# --- Dispatch: web vs desearch ---


@pytest.mark.asyncio
async def test_validate_miner_snippet_web_calls_validate_web_snippet(
    validator, web_evidence
):
    """With source_type=web, only _validate_web_snippet is called (no desearch)."""
    with patch.object(
        validator, "_validate_web_snippet", new_callable=AsyncMock
    ) as mock_web:
        with patch.object(
            validator, "_validate_desearch_snippet", new_callable=AsyncMock
        ) as mock_desearch:
            mock_web.return_value = VericoreStatementResponse(
                url=web_evidence.url,
                excerpt=web_evidence.excerpt,
                domain="example.com",
                snippet_found=True,
                local_score=1.0,
                snippet_score=1.0,
                snippet_score_reason="",
            )
            result = await validator.validate_miner_snippet(
                request_id="req-1",
                miner_uid=0,
                original_statement="Some statement.",
                miner_evidence=web_evidence,
                desearch_response_bodies=None,
            )
            mock_web.assert_called_once()
            mock_desearch.assert_not_called()
            assert result.snippet_found is True
            assert result.domain == "example.com"


@pytest.mark.asyncio
async def test_validate_miner_snippet_desearch_calls_validate_desearch_snippet(
    validator, desearch_evidence
):
    """With source_type=desearch, only _validate_desearch_snippet is called."""
    with patch.object(
        validator, "_validate_web_snippet", new_callable=AsyncMock
    ) as mock_web:
        with patch.object(
            validator, "_validate_desearch_snippet", new_callable=AsyncMock
        ) as mock_desearch:
            mock_desearch.return_value = VericoreStatementResponse(
                url=desearch_evidence.url,
                excerpt=desearch_evidence.excerpt,
                domain="example.com",
                snippet_found=True,
                local_score=1.0,
                snippet_score=1.0,
                snippet_score_reason="",
            )
            result = await validator.validate_miner_snippet(
                request_id="req-1",
                miner_uid=0,
                original_statement="Some statement.",
                miner_evidence=desearch_evidence,
                desearch_response_bodies=[b"fake body"],
            )
            mock_desearch.assert_called_once()
            mock_web.assert_not_called()
            assert result.snippet_found is True


# --- Web path: response shape parity (early exits, no fetch/assess) ---


@pytest.mark.asyncio
async def test_web_no_snippet_provided_returns_same_shape(validator, web_evidence):
    """Web path with empty excerpt returns VericoreStatementResponse with no_snippet_provided."""
    evidence_empty = SourceEvidence(
        url=web_evidence.url,
        excerpt="   ",
        source_type=SourceType.WEB.value,
    )
    with patch.object(
        validator, "validate_miner_url", new_callable=AsyncMock, return_value=None
    ):
        result = await validator.validate_miner_snippet(
            request_id="req-1",
            miner_uid=0,
            original_statement="Some statement.",
            miner_evidence=evidence_empty,
        )
    assert isinstance(result, VericoreStatementResponse)
    assert result.snippet_score_reason == "no_snippet_provided"
    assert result.snippet_found is False
    assert result.domain == "example.com"
    assert result.url == evidence_empty.url
    assert result.excerpt == evidence_empty.excerpt
    assert result.timing is not None
    assert result.verify_miner_time_taken_secs >= 0


@pytest.mark.asyncio
async def test_web_snippet_same_as_statement_returns_same_shape(validator):
    """Web path when excerpt equals statement returns snippet_same_as_statement."""
    statement = "The cat sat on the mat."
    evidence_same = SourceEvidence(
        url="https://example.com/page",
        excerpt=statement,
        source_type=SourceType.WEB.value,
    )
    with patch.object(
        validator, "validate_miner_url", new_callable=AsyncMock, return_value=None
    ):
        result = await validator.validate_miner_snippet(
            request_id="req-1",
            miner_uid=0,
            original_statement=statement,
            miner_evidence=evidence_same,
        )
    assert isinstance(result, VericoreStatementResponse)
    assert result.snippet_score_reason == "snippet_same_as_statement"
    assert result.snippet_found is False
    assert result.domain == "example.com"
    assert result.verify_miner_time_taken_secs >= 0


@pytest.mark.asyncio
async def test_web_exception_returns_error_verifying_miner_snippet(validator):
    """On exception, validate_miner_snippet returns single error response."""
    evidence = SourceEvidence(
        url="https://example.com/page",
        excerpt="Excerpt.",
        source_type=SourceType.WEB.value,
    )
    with patch.object(
        validator, "_validate_web_snippet", new_callable=AsyncMock, side_effect=RuntimeError("fail")
    ):
        result = await validator.validate_miner_snippet(
            request_id="req-1",
            miner_uid=0,
            original_statement="Statement.",
            miner_evidence=evidence,
        )
    assert isinstance(result, VericoreStatementResponse)
    assert result.snippet_score_reason == "error_verifying_miner_snippet"
    assert result.snippet_found is False
    assert result.domain == ""
    assert result.verify_miner_time_taken_secs >= 0
