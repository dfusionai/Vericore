import queue
import argparse
from sentence_transformers import SentenceTransformer, util
from transformers import AutoTokenizer, AutoModel

MAX_VALIDATOR_THREADS = 10

class ContextSimilarityValidator:

    def __init__(self):
        self.tokenizer = AutoTokenizer.from_pretrained("roberta-large-mnli")
        # self.model = AutoModelForSequenceClassification.from_pretrained("roberta-large-mnli")
        self.model = SentenceTransformer('sentence-transformers/all-mpnet-base-v2')

    def get_embeddings(self, text):
        return self.model.encode(text, convert_to_tensor=True)

    def calculate_similarity_score(self, statement: str, excerpt: str):
        # Get embeddings and cosine similarity
        statement_embedding = self.get_embeddings(statement)
        excerpt_embedding = self.get_embeddings(excerpt)

        return float(util.pytorch_cos_sim(statement_embedding, excerpt_embedding).item())


class ContextSimilarityPool:
    def __init__(self, size=5):
        self.pool = queue.Queue(maxsize=size)  # Create a thread-safe queue
        for _ in range(size):
            self.pool.put(ContextSimilarityValidator())  # Fill the pool with instances of SimilarityHandler

    def get_handler(self):
        return self.pool.get()  # Get a handler from the pool (blocking if none available)

    def return_handler(self, handler):
        self.pool.put(handler)  # Return the handler to the pool

pool = ContextSimilarityPool(MAX_VALIDATOR_THREADS)

def calculate_similarity_score(statement: str, excerpt: str):
    handler = pool.get_handler()
    try:
        return handler.calculate_similarity_score(statement, excerpt)
    finally:
        pool.return_handler(handler)

def main(statement:str, snippet: str):
    result = calculate_similarity_score(statement, snippet)
    print(f"RESULT = {result}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Quality Model.")
    parser.add_argument("--statement", type=str, default="The tongue of a giant anteater can extend up to 16 inches (40 centimeters) long, allowing it to reach deep into ant and termite mounds to feed on its favorite prey.", help="Dinosaur existed")
    parser.add_argument("--snippet", type=str, default="he transformative power of financial literacy education cannot be overstated, offering immense benefits that extend well beyond simple money management. By instilling crucial financial skills at an early age, financial literacy workshops empower children and teenagers to make informed decisions that will serve them throughout their lives.")
    args = parser.parse_args()
    main(args.statement, args.snippet)
