import argparse
import asyncio
import sys
import bittensor as bt

from sentence_transformers import SentenceTransformer, util
import threading

SENTENCE_SIMILARITY_THRESHOLD = 0.95

class SimilarityQualityModel:
    """
		Using sentence-transformers (e.g., all-MiniLM-L6-v2 or all-mpnet-base-v2), this model generates sentence embeddings to measure similarity.

		sentence-transformers provides different pretrained models optimized for speed vs accuracy:

		Model	                               Size	    Speed	     Accuracy
		all-MiniLM-L6-v2	                   Small	 ⚡ Fast	   ✅ Good
		paraphrase-MiniLM-L6-v2	             Small	 ⚡ Fast	   ✅ Good
		all-mpnet-base-v2                  	Medium	 🐢 Slower	 🔥 High Accuracy
		paraphrase-mpnet-base-v2	          Medium	 🐢 Slower	 🔥 High Accuracy
		Converts both the snippet text and extracted webpage content into vector representations.
		Computes cosine similarity between embeddings to determine their semantic closeness.
		A similarity score (ranging from 0 to 1) is compared against a predefined threshold (e.g., >0.85).
		A high score indicates a strong semantic match, confirming that the webpage text conveys the same meaning as the snippet.
    """

    def __init__(self):
        self.model = SentenceTransformer("all-MiniLM-L6-v2")  # Lightweight transformer
        # self.model = SentenceTransformer('paraphrase-MiniLM-L6-v2')

    def chunk_text(self, text, window_size=3, step=1):
      """Split text into overlapping chunks of 'window_size' sentences."""
      sentences = text.split(". ")  # Basic sentence splitting (may need better handling)
      chunks = [" ".join(sentences[i: i + window_size]) for i in range(0, len(sentences), step)]
      return chunks

    def verify_similarity(self, snippet_text: str, context_text: str, similarity_threshold=SENTENCE_SIMILARITY_THRESHOLD) :
        # Encode both texts
        snippet_embedding = self.model.encode(snippet_text, convert_to_tensor=True)

        chunks = self.chunk_text(context_text, window_size=3)

        chunk_embeddings = self.model.encode(chunks, convert_to_tensor=True)

        similarities = util.pytorch_cos_sim(snippet_embedding, chunk_embeddings)
        best_score = similarities.max().item()

        return best_score > similarity_threshold, best_score   # Return best match score and decision

similarity_quality_model = SimilarityQualityModel()
model_lock = threading.Lock()

async def verify_text_similarity(snippet_text: str, context_text: str, similarity_threshold=SENTENCE_SIMILARITY_THRESHOLD) :
    return await asyncio.to_thread(similarity_quality_model.verify_similarity, snippet_text, context_text, similarity_threshold)

async def main(snippet_text:str, context_text:str):
    score = await verify_text_similarity(snippet_text, context_text)

    print(f"Match: {score}"  )

# Used for testing purposes
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Quality Model.")
    parser.add_argument("--statement", type=str, default="Narwhals are known for their long, spiral tusks, which are actually elongated teeth that can grow up to 10 feet (3 meters) in length, making them one of the most unique marine mammals in the Arctic.", help="Dinosaur existed")
    parser.add_argument("--snippet", type=str, default="...Narwhals are known for their long, spiral tusks, which are actually elongated teeth that can grow up to 10 feet (3 meters) in length, making them one of the most unique marine mammals in the Arctic...", help="Dinosaur existed in the Jurassic Period")
    args = parser.parse_args()

    asyncio.run(main(args.statement, args.snippet))


