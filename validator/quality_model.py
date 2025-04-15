import torch
import threading
from transformers import RobertaTokenizer, RobertaForSequenceClassification

class VeridexQualityModel:
    """
    Example Quality Model using roberta-large-mnli (or roberta-base-mnli).
    This model's classification head typically returns:
      index 0 -> CONTRADICTION
      index 1 -> NEUTRAL
      index 2 -> ENTAILMENT

    We'll compute a probability distribution via softmax(logits).
    Then, define a custom "score" formula that rewards contradiction or entailment
    and penalizes strongly neutral.
    """

    def __init__(self, model_name='roberta-large-mnli'):
        self.model_name = model_name
        self.model = RobertaForSequenceClassification.from_pretrained(model_name)
        self.tokenizer = RobertaTokenizer.from_pretrained(model_name)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model.to(self.device)
        self.model.eval()

    def score_pair_distrib(self, statement: str, snippet: str):
        """
        Compute the probability distribution over [contradiction, neutral, entailment].

        Returns:
          probs: dict of {
              "contradiction": float,
              "neutral": float,
              "entailment": float
          }
          local_score: a float derived from these probabilities.

        Default formula:
            local_score = (prob_contra + prob_entail) - (prob_neutral)
        """
        inputs = self.tokenizer(statement, snippet, return_tensors='pt',
                                truncation=True, padding=True)
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        with torch.no_grad():
            logits = self.model(**inputs).logits
            # logits.shape = [batch_size, 3]
            probs_tensor = torch.softmax(logits, dim=-1)[0]  # [3]
            prob_contra = probs_tensor[0].item()
            prob_neutral = probs_tensor[1].item()
            prob_entail = probs_tensor[2].item()

        local_score = (prob_contra + prob_entail) - (prob_neutral)
        return {
            "contradiction": prob_contra,
            "neutral": prob_neutral,
            "entailment": prob_entail
        }, local_score

    def score_statement_snippets(self, statement: str, snippet_texts: list) -> (float, list):
        """
        If you have multiple evidence snippets, we compute
        a distribution and local score for each snippet,
        then average them to get a combined_score.

        Returns:
          combined_score: float
          snippet_distributions: list of dicts, each with
            {
              "contradiction": float,
              "neutral": float,
              "entailment": float,
              "local_score": float
            }
        """
        if not snippet_texts:
            return 0.0, []

        snippet_distributions = []
        total_score = 0.0

        for snippet_str in snippet_texts:
            probs, local_score = self.score_pair_distrib(statement, snippet_str)
            snippet_distributions.append({
                "contradiction": probs["contradiction"],
                "neutral": probs["neutral"],
                "entailment": probs["entailment"],
                "local_score": local_score
            })
            total_score += local_score

        combined_score = total_score / len(snippet_texts)
        return combined_score, snippet_distributions


verify_quality_model = VeridexQualityModel()
model_lock = threading.Lock()

def score_statement_snippets(statement: str, snippet_texts: list) -> (float, list):
  with model_lock:
      return verify_quality_model.score_statement_snippets(statement, snippet_texts)

def score_statement_distribution(statement: str, snippet: str):
    with model_lock:
        return verify_quality_model.score_pair_distrib(statement, snippet)

