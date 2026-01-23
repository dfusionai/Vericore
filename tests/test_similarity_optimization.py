"""
Test to verify that the optimized batch encoding produces the same results as the original method.
"""
import time
import threading
from sentence_transformers import SentenceTransformer, util

SENTENCE_SIMILARITY_THRESHOLD = 0.95


class OldSimilarityModel:
    """Original implementation with 2 separate encode calls."""
    
    def __init__(self):
        self.model = SentenceTransformer("all-MiniLM-L6-v2")
        self.lock = threading.Lock()

    def chunk_text(self, text, window_size=3, step=1):
        sentences = text.split(". ")
        chunks = [" ".join(sentences[i: i + window_size]) for i in range(0, len(sentences), step)]
        return chunks

    def verify_similarity(self, snippet_text: str, context_text: str, similarity_threshold=SENTENCE_SIMILARITY_THRESHOLD):
        # Original: 2 separate encode calls
        snippet_embedding = self.model.encode(snippet_text, convert_to_tensor=True)
        chunks = self.chunk_text(context_text, window_size=3)
        chunk_embeddings = self.model.encode(chunks, convert_to_tensor=True)
        
        with self.lock:
            similarities = util.pytorch_cos_sim(snippet_embedding, chunk_embeddings)
        
        best_score = similarities.max().item()
        return best_score > similarity_threshold, best_score


class NewSimilarityModel:
    """Optimized implementation with batched encoding."""
    
    def __init__(self):
        self.model = SentenceTransformer("all-MiniLM-L6-v2")
        self.lock = threading.Semaphore(3)

    def chunk_text(self, text, window_size=3, step=1):
        sentences = text.split(". ")
        chunks = [" ".join(sentences[i: i + window_size]) for i in range(0, len(sentences), step)]
        return chunks

    def verify_similarity(self, snippet_text: str, context_text: str, similarity_threshold=SENTENCE_SIMILARITY_THRESHOLD):
        chunks = self.chunk_text(context_text, window_size=3)
        
        # Optimized: Single batched encode call
        all_texts = [snippet_text] + chunks
        
        with self.lock:
            all_embeddings = self.model.encode(all_texts, convert_to_tensor=True, batch_size=32)
        
        snippet_embedding = all_embeddings[0:1]
        chunk_embeddings = all_embeddings[1:]
        
        if len(chunk_embeddings) == 0:
            return False, 0.0
        
        similarities = util.pytorch_cos_sim(snippet_embedding, chunk_embeddings)
        best_score = similarities.max().item()
        return best_score > similarity_threshold, best_score


# Test cases
TEST_CASES = [
    {
        "name": "Exact match",
        "snippet": "The quick brown fox jumps over the lazy dog.",
        "context": "The quick brown fox jumps over the lazy dog. This is a common pangram used in typing tests."
    },
    {
        "name": "Similar content",
        "snippet": "Narwhals are known for their long, spiral tusks.",
        "context": "Narwhals are fascinating marine mammals. They are known for their long, spiral tusks. These tusks can grow up to 10 feet in length. They live in Arctic waters."
    },
    {
        "name": "Unrelated content",
        "snippet": "The stock market closed higher today.",
        "context": "Elephants are the largest land animals. They have long trunks and big ears. African elephants are larger than Asian elephants."
    },
    {
        "name": "Long context",
        "snippet": "Machine learning models require large datasets.",
        "context": "Artificial intelligence has transformed many industries. Machine learning models require large datasets for training. Deep learning is a subset of machine learning. Neural networks are inspired by the human brain. Data preprocessing is crucial for model performance. Feature engineering can improve accuracy. Hyperparameter tuning optimizes model behavior. Cross-validation helps prevent overfitting. Regularization techniques reduce model complexity. Transfer learning leverages pre-trained models."
    },
    {
        "name": "Short context",
        "snippet": "Hello world",
        "context": "Hello world"
    },
]


def run_tests():
    print("Loading models...")
    old_model = OldSimilarityModel()
    new_model = NewSimilarityModel()
    print("Models loaded.\n")
    
    print("=" * 80)
    print("COMPARING OLD vs NEW SIMILARITY METHODS")
    print("=" * 80)
    
    all_passed = True
    old_total_time = 0
    new_total_time = 0
    
    for i, test in enumerate(TEST_CASES, 1):
        print(f"\nTest {i}: {test['name']}")
        print("-" * 40)
        
        # Run old method
        start = time.perf_counter()
        old_result, old_score = old_model.verify_similarity(test["snippet"], test["context"])
        old_time = time.perf_counter() - start
        old_total_time += old_time
        
        # Run new method
        start = time.perf_counter()
        new_result, new_score = new_model.verify_similarity(test["snippet"], test["context"])
        new_time = time.perf_counter() - start
        new_total_time += new_time
        
        # Compare results
        score_diff = abs(old_score - new_score)
        results_match = old_result == new_result and score_diff < 1e-6
        
        status = "✅ PASS" if results_match else "❌ FAIL"
        
        print(f"  Old: result={old_result}, score={old_score:.6f}, time={old_time*1000:.2f}ms")
        print(f"  New: result={new_result}, score={new_score:.6f}, time={new_time*1000:.2f}ms")
        print(f"  Score diff: {score_diff:.10f}")
        print(f"  Status: {status}")
        
        if not results_match:
            all_passed = False
    
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total old method time: {old_total_time*1000:.2f}ms")
    print(f"Total new method time: {new_total_time*1000:.2f}ms")
    print(f"Speedup: {old_total_time/new_total_time:.2f}x" if new_total_time > 0 else "N/A")
    print(f"\nAll tests passed: {'✅ YES' if all_passed else '❌ NO'}")
    
    return all_passed


def run_concurrent_test():
    """Test concurrent execution to verify thread safety."""
    import concurrent.futures
    
    print("\n" + "=" * 80)
    print("CONCURRENT EXECUTION TEST")
    print("=" * 80)
    
    new_model = NewSimilarityModel()
    
    def run_similarity(test_case):
        return new_model.verify_similarity(test_case["snippet"], test_case["context"])
    
    # Run all test cases concurrently
    start = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(run_similarity, tc) for tc in TEST_CASES * 3]  # 15 concurrent calls
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    concurrent_time = time.perf_counter() - start
    
    # Run sequentially for comparison
    start = time.perf_counter()
    for tc in TEST_CASES * 3:
        run_similarity(tc)
    sequential_time = time.perf_counter() - start
    
    print(f"15 calls sequential: {sequential_time*1000:.2f}ms")
    print(f"15 calls concurrent: {concurrent_time*1000:.2f}ms")
    print(f"Concurrency benefit: {sequential_time/concurrent_time:.2f}x faster")


if __name__ == "__main__":
    passed = run_tests()
    run_concurrent_test()
    
    exit(0 if passed else 1)
