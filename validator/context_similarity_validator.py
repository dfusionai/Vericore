import argparse
import threading
from sentence_transformers import SentenceTransformer, util

MAX_CONCURRENT_CONTEXT_OPS = 5  # Max concurrent context similarity operations


class ContextSimilarityValidator:
    """Singleton validator with batched encoding for better performance."""

    def __init__(self):
        self.model = SentenceTransformer('sentence-transformers/all-mpnet-base-v2')
        self.lock = threading.Semaphore(MAX_CONCURRENT_CONTEXT_OPS)

    def calculate_similarity_score(self, statement: str, excerpt: str):
        # Batch encode both texts in a single call (much faster than separate calls)
        with self.lock:
            embeddings = self.model.encode([statement, excerpt], convert_to_tensor=True, batch_size=2)
        
        statement_embedding = embeddings[0:1]
        excerpt_embedding = embeddings[1:2]

        return float(util.pytorch_cos_sim(statement_embedding, excerpt_embedding).item())


# Single shared validator instance (no pool needed with semaphore)
_validator = ContextSimilarityValidator()


def calculate_similarity_score(statement: str, excerpt: str):
    return _validator.calculate_similarity_score(statement, excerpt)

def main(statement:str, snippet: str):
    result = calculate_similarity_score(statement, snippet)
    print(f"RESULT = {result}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Quality Model.")
    parser.add_argument("--statement", type=str, default="The lifespan of a typical housefly is about 15 to 30 days, depending on environmental conditions, illustrating the brevity of life for many insects.", help="Dinosaur existed")
    parser.add_argument("--snippet", type=str, default="Ethereum is a decentralized blockchain")
    args = parser.parse_args()
    main(args.statement, args.snippet)
