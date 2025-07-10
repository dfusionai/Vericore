import argparse

import torch
import asyncio
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
        inputs = self.tokenizer(
            text=snippet,        # premise/snippet
            text_pair=statement, # hypothesis/statement
            return_tensors='pt',
            truncation=True,
            padding=True
        )
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        with model_lock:
            with torch.no_grad():
                logits = self.model(**inputs).logits
                # logits.shape = [batch_size, 3]
                probs_tensor = torch.softmax(logits, dim=-1)[0]  # [3]
                prob_contra = probs_tensor[0].item()
                prob_neutral = probs_tensor[1].item()
                prob_entail = probs_tensor[2].item()

        # local_score = (prob_contra + prob_entail) - (prob_neutral)
        # don't minus neutrality score
        local_score = (prob_contra + prob_entail)
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

model_lock = threading.Semaphore(5)

async def score_statement_snippets(statement: str, snippet_texts: list) -> (float, list):
    return await asyncio.to_thread(verify_quality_model.score_statement_snippets, statement, snippet_texts)

async def score_statement_distribution(statement: str, snippet: str) -> (float, list):
    return await asyncio.to_thread(verify_quality_model.score_pair_distrib,statement, snippet)

async def main(statement:str, snippet: str):
    print(f"statement={statement}, snippet={snippet}")
    result = await score_statement_distribution(statement, snippet)
    print(result)


# Used for testing purposes
# run:
# python -m quality_model --statement "Dinosaur existed" --snippet "Dinosaur existed in the Jurassic Period"
# python -m validator.quality_model --statement "birds have feathers" --snippet "All birds have feathers and most can fly"
# ({'contradiction': 0.6786971092224121, 'neutral': 0.3057457208633423, 'entailment': 0.015557228587567806}, 0.38850861694663763)
# python -m validator.quality_model --statement "All birds have feathers" --snippet "Cats have tails"
# ({'contradiction': 0.8573225736618042, 'neutral': 0.12920480966567993, 'entailment': 0.013472586870193481}, 0.7415903508663177)
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Quality Model.")
    parser.add_argument("--statement", type=str, default="The blue whale's tongue can weigh as much as an elephant, underscoring the immense size of the largest animal on Earth.", help="Dinosaur existed")
    parser.add_argument("--snippet", type=str, default="The ostrich, Earth's largest bird, stands out with a unique foot structure. Unlike flying birds with four toes, or other flightless birds with three, the ostrich is singular in possessing two toes per foot. Remarkably, one substantial toe resembling a hoof bears the bird's weight, while a smaller toe aids in balance", help="Dinosaur existed in the Jurassic Period")
    args = parser.parse_args()

    asyncio.run(main(args.statement, args.snippet))
