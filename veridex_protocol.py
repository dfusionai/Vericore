import typing
import bittensor as bt

class SourceEvidence(typing.NamedTuple):
    """
    Container for a single piece of evidence from a miner.
    """
    url: str
    xpath: str
    start_char: int
    end_char: int
    # Optionally store the excerpt text if the miner chooses to provide it.
    # Some miners might skip excerpt to save bandwidth, 
    # and the validator can fetch it later by using the URL+xpath+offset.
    excerpt: str = ""

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
