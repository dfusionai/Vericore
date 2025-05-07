from typing import List
from dataclasses import dataclass, field, asdict


@dataclass
class ValidatorResultsData:
    unique_id: str = ""
    block_number: int = -1
    validator_uid: int = -1
    validator_hotkey: str = ""
    timestamp: float = 0
    has_summary_data: bool = False
    vericore_responses: List[dict] = field(default_factory=list)
    calculated_weights: List[float] = field(default_factory=list)
    incentives: List[float] = field(default_factory=list)
    moving_scores: List[float] = field(default_factory=list)
