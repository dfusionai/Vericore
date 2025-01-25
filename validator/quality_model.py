import torch
from transformers import RobertaTokenizer, RobertaForSequenceClassification
import bittensor as bt

class VeridexQualityModel:
    """
    Example Quality Model using roberta-large-mnli.
    This model's classification head typically returns:
      - 0 -> CONTRADICTION
      - 1 -> NEUTRAL
      - 2 -> ENTAILMENT
    We adapt that to a "quality" or "alignment" score 
    for the validator's aggregator logic. 
    """

    def __init__(self, model_name='roberta-large-mnli'):
        self.model_name = model_name
        self.model = RobertaForSequenceClassification.from_pretrained(model_name)
        self.tokenizer = RobertaTokenizer.from_pretrained(model_name)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model.to(self.device)
        self.model.eval()

    def score_pair(self, statement: str, snippet: str) -> float:
        """
        Returns a real-valued quality score. 
        For example:
          - ENT -> +1.0
          - CONTRADICTION -> +1.0
          - NEUTRAL -> 0.0
        Because both entailed or contradicted means it's providing a 
        potential verification or falsification. 
        Neutral means it doesn't help confirm or deny.
        """
        inputs = self.tokenizer(statement, snippet, return_tensors='pt',
                                truncation=True, padding=True)
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        with torch.no_grad():
            logits = self.model(**inputs).logits
            pred = torch.argmax(logits, dim=-1).item()

        # roberta-large-mnli label mapping: 0=contradiction, 1=neutral, 2=entailment
        # We'll define a simple scoring scheme:
        if pred == 1:  # neutral
            return 0.0
        else:
            # contradiction or entailment
            return 1.0

    def score_statement_snippets(self, statement: str, snippets: list) -> float:
        """
        If you have multiple evidence snippets, you can sum or average them.
        Return a single numeric "quality" measure for all snippets combined.
        """
        if not snippets:
            return 0.0

        total = 0.0
        for snippet in snippets:
            total += self.score_pair(statement, snippet)

        # Example: average
        return total / len(snippets)
