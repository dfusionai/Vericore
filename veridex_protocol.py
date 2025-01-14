import typing
import bittensor as bt

class VeridexSynapse(bt.Synapse):
    """
    Veridex protocol:
    Pass a 'statement' (str) plus an optional list of 'sources' (List[str]).
    The miner responds with a 'veridex_response' which is a list of
    (url, xpath) that corroborates or refutes the statement.
    """

    statement: str
    sources: typing.List[str] = []
    veridex_response: typing.Optional[typing.List[typing.Tuple[str, str]]] = None
