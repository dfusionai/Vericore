# veridex_protocol.py
import typing
from dataclasses import dataclass, field

import bittensor as bt

class SourceEvidence(typing.NamedTuple):
    """
    Container for a single piece of evidence from a miner.
    """
    url: str
    excerpt: str = ""  # The snippet text the miner claims is from the URL

class VeridexSynapse(bt.Synapse):
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

@dataclass
class VeridexResponse:
   synapse: VeridexSynapse
   elapse_time: float

@dataclass
class VericoreStatementResponse():
  url: str
  excerpt: str
  domain: str
  snippet_found: bool
  local_score: float
  snippet_score: float
  domain_factor: float = 0
  contradiction: float = 0
  neutral: float = 0
  entailment: float = 0

@dataclass
class VericoreMinerStatementResponse():
  miner_hotkey: str
  miner_uid: float
  status: str
  vericore_responses: typing.List["VericoreStatementResponse"] = field(default_factory=list)
  speed_factor: float = 0
  raw_score: float = 0
  final_score: float = 0

@dataclass
class VericoreQueryResponse():
  status: str
  request_id: str
  statement: str
  sources: list
  results: typing.List["VericoreMinerStatementResponse"] = field(default_factory=list)
