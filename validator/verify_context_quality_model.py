import argparse
import asyncio
import sys
import bittensor as bt

from sentence_transformers import SentenceTransformer, util
import threading

class VerifyContextQualityModel:
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

    def verify_context(self, snippet_text: str, context_text: str) :

        threshold = 0.75
        # Encode both texts
        snippet_embedding = self.model.encode(snippet_text, convert_to_tensor=True)

        chunks = self.chunk_text(context_text, window_size=3)

        chunk_embeddings = self.model.encode(chunks, convert_to_tensor=True)

        similarities = util.pytorch_cos_sim(snippet_embedding, chunk_embeddings)
        best_score = similarities.max().item()

        # context_embedding = self.model.encode(context_text, convert_to_tensor=True)
        # Compare snippet against each chunk
        # best_score = 0
        # for chunk in chunks:
        #    chunk_embedding = self.model.encode(chunk, convert_to_tensor=True)
        #    similarity = util.pytorch_cos_sim(snippet_embedding, chunk_embedding).item()
        #    best_score = max(best_score, similarity)  # Keep highest similarity

        return best_score > threshold, best_score   # Return best match score and decision

verify_quality_model = VerifyContextQualityModel()
model_lock = threading.Lock()

async def verify_context_quality(snippet_text: str, context_text: str) :
    return await asyncio.to_thread(verify_quality_model.verify_context, snippet_text, context_text)

async def main(snippet_text:str, context_text:str):
    score = await verify_context_quality(snippet_text, context_text)

    print(f"Match: {score}"  )

# Used for testing purposes
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Quality Model.")
    parser.add_argument("--statement", type=str, default="Dinosaur existed", help="Dinosaur existed")
    parser.add_argument("--snippet", type=str, default="Dinosaur existed in the Jurassic Period", help="Dinosaur existed in the Jurassic Period")
    args = parser.parse_args()

    asyncio.run(main(args.statement, args.snippet))


