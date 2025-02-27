import sys

from sentence_transformers import SentenceTransformer, util

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

    def verify_context(self, snippet_text: str, context_text: str) -> bool:
        # Encode both texts
        snippet_embedding = self.model.encode(snippet_text, convert_to_tensor=True)
        context_embedding = self.model.encode(context_text, convert_to_tensor=True)

        # Compute cosine similarity
        similarity_score = util.pytorch_cos_sim(snippet_embedding, context_embedding).item()
        print(f"snippet_embedding {snippet_text}: {similarity_score}")
        # Define a threshold (adjust as needed)
        return similarity_score >= 0.80

# Used for testing purposes
if __name__ == "__main__":
    if len(sys.argv) < 3:
      print("Usage: python similarity_check.py '<snippet>' '<context>'")
      sys.exit(1)

    snippet = sys.argv[1]
    context = sys.argv[2]
    model = VerifyContextQualityModel()
    score = model.verify_context(snippet, context)

    print("Match:", score > 0.95)
