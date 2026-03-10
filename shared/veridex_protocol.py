# veridex_protocol.py
import typing
from dataclasses import dataclass, field
from enum import Enum

import bittensor as bt

# Snippet fetcher status constants (fetch-by-HTTP and fetch-by-Selenium)
SNIPPET_FETCHER_STATUS_OK = "ok"
SNIPPET_FETCHER_STATUS_ERROR = "error"
SNIPPET_FETCHER_STATUS_NOT_RUN = "not_run"


@dataclass
class FetchPageResult:
    """Result of fetching a page (HTTP and/or Selenium). Use constants for status fields.
    All fields default to failure/not-run values so FetchPageResult() is a valid empty result.
    """
    cleaned_html: str = ""
    fetch_by_http_time_secs: float = -1.0  # -1 if NA
    fetch_by_selenium_time_secs: float = -1.0  # -1 if NA
    cleaning_html_time_secs: float = -1.0  # -1 if not run
    fetch_by_http_status: str = SNIPPET_FETCHER_STATUS_NOT_RUN  # SNIPPET_FETCHER_STATUS_*
    fetch_by_selenium_status: str = SNIPPET_FETCHER_STATUS_NOT_RUN


@dataclass
class StatementResponseTiming:
    """Timing and fetcher status for a single snippet validation."""
    verify_miner_time_taken_secs: float = 0
    fetch_page_time_taken_secs: float = 0
    assess_statement_time_taken_secs: float = 0
    fetch_by_http_time_secs: float = -1
    fetch_by_selenium_time_secs: float = -1
    snippet_fetcher_total_time_secs: float = -1
    cleaning_html_time_taken_secs: float = -1
    fetch_by_http_status: str = SNIPPET_FETCHER_STATUS_NOT_RUN
    fetch_by_selenium_status: str = SNIPPET_FETCHER_STATUS_NOT_RUN


@dataclass
class MinerResponseTiming:
    """Aggregated timing for a miner's response."""
    elapsed_time: float = 0
    total_fetch_time_secs: float = 0
    total_ai_time_secs: float = 0
    total_other_time_secs: float = 0
    avg_snippet_time_secs: float = 0
    max_snippet_time_secs: float = 0
    snippet_count: int = 0


@dataclass
class QueryResponseTiming:
    """Aggregated timing for a full query response."""
    total_elapsed_time: float = 0
    timestamp: float = 0
    total_fetch_time_secs: float = 0
    total_ai_time_secs: float = 0
    total_other_time_secs: float = 0
    avg_snippet_time_secs: float = 0
    max_snippet_time_secs: float = 0
    total_snippet_count: int = 0
    miner_count: int = 0


class SourceType(str, Enum):
    """Source type for evidence. Wire format is the string value."""
    WEB = "web"
    DESEARCH = "desearch"


class SourceEvidence(typing.NamedTuple):
    """
    Container for a single piece of evidence from a miner.
    source_type: SourceType.WEB or SourceType.DESEARCH (wire format: "web" | "desearch").
    """
    url: str
    excerpt: str = ""  # The snippet text the miner claims is from the URL
    source_type: str = "web"  # SourceType.WEB.value | SourceType.DESEARCH.value


@dataclass
class DesearchProof:
    """Proof headers from Desearch API response (X-Proof-Signature, X-Proof-Timestamp, X-Proof-Expiry)."""
    signature: str = ""  # hex
    timestamp: str = ""
    expiry: str = ""


@dataclass
class Desearch:
    """Full Desearch response on the synapse: body (base64) and proof from response headers."""
    response_body: str = ""  # base64-encoded full Desearch response body
    proof: DesearchProof = field(default_factory=DesearchProof)


class VericoreSynapse(bt.Synapse):
    """
    Veridex protocol:
    Inputs:
      - statement (str)
      - sources (List[str]) [Optional "preferred" sources, or references]
    Outputs:
      - veridex_response: A list of SourceEvidence items.
        Each describes a snippet that corroborates or refutes the statement.
    """
    request_id: str = None
    statement: str
    sources: typing.List[str] = []
    veridex_response: typing.Optional[typing.List[SourceEvidence]] = None
    desearch: typing.Optional[typing.List[Desearch]] = None

@dataclass
class VeridexResponse:
   synapse: VericoreSynapse
   elapse_time: float

@dataclass
class VericoreStatementResponse():
  url: str
  excerpt: str
  domain: str
  snippet_found: bool
  local_score: float
  snippet_score: float
  snippet_score_reason: str = ""
  rejection_reason: str = ""
  domain_factor: float = 0
  contradiction: float = 0
  neutral: float = 0
  entailment: float = 0
  context_similarity_score:float=0
  statement_similarity_score: float = 0
  is_similar_context: bool=False
  approved_url_multiplier:float=0
  page_text: str = ""
  assessment_result: dict = field(default_factory=dict)
  verify_miner_time_taken_secs: float=0
  fetch_page_time_taken_secs: float=0  # Legacy: end-to-end fetch step time; prefer snippet_fetcher_* for breakdown
  assess_statement_time_taken_secs: float=0
  snippet_fetcher_http_time_secs: float = -1  # HTTP request time from snippet fetcher; -1 if NA (legacy)
  snippet_fetcher_selenium_time_secs: float = -1  # Selenium fallback time from snippet fetcher; -1 if NA (legacy)
  snippet_fetcher_total_time_secs: float = -1  # Total snippet fetcher time (http + selenium when both used); -1 if NA
  cleaning_html_time_taken_secs: float = -1  # Time spent in clean_html; -1 if not run
  fetch_by_http_status: str = SNIPPET_FETCHER_STATUS_NOT_RUN  # SNIPPET_FETCHER_STATUS_*
  fetch_by_selenium_status: str = SNIPPET_FETCHER_STATUS_NOT_RUN  # SNIPPET_FETCHER_STATUS_*
  timing: typing.Optional["StatementResponseTiming"] = None  # Nested timing DTO; legacy fields above kept for compatibility
  sentiment: float = 0.0
  conviction: float = 0.0
  source_credibility: float = 0.0
  narrative_momentum: float = 0.0
  risk_reward_sentiment: float = 0.0
  catalyst_detection: float = 0.0
  political_leaning: float = 0.0
  social_bonus_contribution: float = 0.0  # This excerpt's contribution to miner social_bonus_score (0, 0.5, or 1.0)

@dataclass
class VericoreMinerStatementResponse():
  miner_hotkey: str
  miner_uid: int
  status: str
  vericore_responses: typing.List["VericoreStatementResponse"] = field(default_factory=list)
  speed_factor: float = 0
  raw_score: float = 0
  final_score: float = 0
  elapsed_time: float = 0
  # Performance stats (aggregated across all snippets)
  total_fetch_time_secs: float = 0
  total_ai_time_secs: float = 0
  total_other_time_secs: float = 0
  avg_snippet_time_secs: float = 0
  max_snippet_time_secs: float = 0
  snippet_count: int = 0
  timing: typing.Optional["MinerResponseTiming"] = None  # Nested timing DTO
  desearch_bonus_score: float = 0.0  # Miner-level desearch proof bonus/penalty
  social_bonus_score: float = 0.0  # Sum of per-snippet social bonus (desearch only: x.com +1, reddit.com +0.5)

@dataclass
class VericoreQueryResponse():
  validator_hotkey: str
  validator_uid: int
  status: str
  request_id: str
  statement: str
  sources: list
  timestamp: float = 0
  total_elapsed_time: float = 0
  results: typing.List["VericoreMinerStatementResponse"] = field(default_factory=list)
  # Performance stats (aggregated across all miners/snippets)
  total_fetch_time_secs: float = 0
  total_ai_time_secs: float = 0
  total_other_time_secs: float = 0
  avg_snippet_time_secs: float = 0
  max_snippet_time_secs: float = 0
  total_snippet_count: int = 0
  miner_count: int = 0
  timing: typing.Optional["QueryResponseTiming"] = None  # Nested timing DTO
