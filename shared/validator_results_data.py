from typing import List
from dataclasses import dataclass, field, asdict


@dataclass
class ValidatorResultsData:
    """
    All list fields (calculated_weights, incentives, moving_scores) are indexed by UID:
    index i = value for UID i. Dashboard must use e.g. calculated_weights[uid], not
    calculated_weights[row_index]. Validators get 0 calculated weight by design.
    """
    unique_id: str = ""
    block_number: int = -1
    validator_uid: int = -1
    validator_hotkey: str = ""
    timestamp: float = 0
    has_summary_data: bool = False
    vericore_responses: List[dict] = field(default_factory=list)
    calculated_weights: List[float] = field(default_factory=list)  # indexed by UID
    incentives: List[float] = field(default_factory=list)  # indexed by UID; on-chain (previous epoch / pre-reveal)
    moving_scores: List[float] = field(default_factory=list)  # indexed by UID
    validator_uids: List[int] = field(default_factory=list)
    burn_uid: int = -1  # Emission control UID; dashboard can show this miner first (has most incentives)
