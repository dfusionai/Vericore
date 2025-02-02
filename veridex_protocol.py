# veridex_protocol.py
import typing
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
    statement: str
    sources: typing.List[str] = []
    veridex_response: typing.Optional[typing.List[SourceEvidence]] = None
