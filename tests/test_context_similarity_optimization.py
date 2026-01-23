"""
Test to verify that the optimized context similarity validator produces the same results as the original method.
"""
import time
import threading
import queue
from sentence_transformers import SentenceTransformer, util


class OldContextSimilarityValidator:
    """Original implementation with pool and 2 separate encode calls."""

    def __init__(self):
        self.model = SentenceTransformer('sentence-transformers/all-mpnet-base-v2')

    def get_embeddings(self, text):
        return self.model.encode(text, convert_to_tensor=True)

    def calculate_similarity_score(self, statement: str, excerpt: str):
        # Original: 2 separate encode calls
        statement_embedding = self.get_embeddings(statement)
        excerpt_embedding = self.get_embeddings(excerpt)
        return float(util.pytorch_cos_sim(statement_embedding, excerpt_embedding).item())


class OldContextSimilarityPool:
    """Original pool-based approach with blocking queue."""
    
    def __init__(self, size=5):
        self.pool = queue.Queue(maxsize=size)
        for _ in range(size):
            self.pool.put(OldContextSimilarityValidator())

    def get_handler(self):
        return self.pool.get()  # Blocking if none available

    def return_handler(self, handler):
        self.pool.put(handler)


class NewContextSimilarityValidator:
    """Optimized implementation with batched encoding and semaphore."""

    def __init__(self):
        self.model = SentenceTransformer('sentence-transformers/all-mpnet-base-v2')
        self.lock = threading.Semaphore(5)

    def calculate_similarity_score(self, statement: str, excerpt: str):
        # Optimized: Single batched encode call
        with self.lock:
            embeddings = self.model.encode([statement, excerpt], convert_to_tensor=True, batch_size=2)
        
        statement_embedding = embeddings[0:1]
        excerpt_embedding = embeddings[1:2]
        return float(util.pytorch_cos_sim(statement_embedding, excerpt_embedding).item())


# Test cases
TEST_CASES = [
    {
        "name": "High similarity - same topic",
        "statement": "The Great Pyramid of Giza was built around 2580-2560 BC.",
        "excerpt": "Built for King Khufu and dating about 2589-2566 BC, the Great Pyramid of Giza is the oldest and largest of the three pyramids."
    },
    {
        "name": "Medium similarity - related topic",
        "statement": "Electric vehicles are becoming more popular.",
        "excerpt": "Sales of battery-powered cars have increased significantly in recent years as consumers seek alternatives to gasoline vehicles."
    },
    {
        "name": "Low similarity - different topics",
        "statement": "The stock market reached new highs today.",
        "excerpt": "Elephants are the largest land animals on Earth, known for their intelligence and social behavior."
    },
    {
        "name": "Exact match",
        "statement": "Machine learning models require large datasets for training.",
        "excerpt": "Machine learning models require large datasets for training."
    },
    {
        "name": "Long excerpt",
        "statement": "Climate change affects global weather patterns.",
        "excerpt": "Climate change is causing significant shifts in global weather patterns, leading to more frequent and intense storms, droughts, and heat waves. Scientists have documented rising temperatures, melting ice caps, and rising sea levels as evidence of these changes. The impact on ecosystems and human societies is becoming increasingly apparent."
    },
    {
        "name": "Short texts",
        "statement": "AI is transforming industries.",
        "excerpt": "Artificial intelligence transforms business."
    },
]


def run_tests():
    print("Loading models (this may take a moment for all-mpnet-base-v2)...")
    
    # Create old-style pool
    old_pool = OldContextSimilarityPool(size=2)  # Smaller pool for testing
    
    # Create new-style validator
    new_validator = NewContextSimilarityValidator()
    
    print("Models loaded.\n")
    
    print("=" * 80)
    print("COMPARING OLD vs NEW CONTEXT SIMILARITY METHODS")
    print("=" * 80)
    
    all_passed = True
    old_total_time = 0
    new_total_time = 0
    
    for i, test in enumerate(TEST_CASES, 1):
        print(f"\nTest {i}: {test['name']}")
        print("-" * 40)
        
        # Run old method (with pool)
        start = time.perf_counter()
        handler = old_pool.get_handler()
        try:
            old_score = handler.calculate_similarity_score(test["statement"], test["excerpt"])
        finally:
            old_pool.return_handler(handler)
        old_time = time.perf_counter() - start
        old_total_time += old_time
        
        # Run new method
        start = time.perf_counter()
        new_score = new_validator.calculate_similarity_score(test["statement"], test["excerpt"])
        new_time = time.perf_counter() - start
        new_total_time += new_time
        
        # Compare results
        score_diff = abs(old_score - new_score)
        results_match = score_diff < 1e-6
        
        status = "✅ PASS" if results_match else "❌ FAIL"
        
        print(f"  Old: score={old_score:.6f}, time={old_time*1000:.2f}ms")
        print(f"  New: score={new_score:.6f}, time={new_time*1000:.2f}ms")
        print(f"  Score diff: {score_diff:.10f}")
        print(f"  Status: {status}")
        
        if not results_match:
            all_passed = False
    
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total old method time: {old_total_time*1000:.2f}ms")
    print(f"Total new method time: {new_total_time*1000:.2f}ms")
    if new_total_time > 0:
        print(f"Speedup: {old_total_time/new_total_time:.2f}x")
    print(f"\nAll tests passed: {'✅ YES' if all_passed else '❌ NO'}")
    
    return all_passed


def run_concurrent_test():
    """Test concurrent execution to verify thread safety and measure contention."""
    import concurrent.futures
    
    print("\n" + "=" * 80)
    print("CONCURRENT EXECUTION TEST")
    print("=" * 80)
    
    # Old pool with limited handlers (simulating contention)
    old_pool = OldContextSimilarityPool(size=3)
    
    # New validator with semaphore
    new_validator = NewContextSimilarityValidator()
    
    def run_old_similarity(test_case):
        handler = old_pool.get_handler()
        try:
            return handler.calculate_similarity_score(test_case["statement"], test_case["excerpt"])
        finally:
            old_pool.return_handler(handler)
    
    def run_new_similarity(test_case):
        return new_validator.calculate_similarity_score(test_case["statement"], test_case["excerpt"])
    
    num_concurrent = 12  # More than pool size to show contention
    test_cases_repeated = (TEST_CASES * 2)[:num_concurrent]
    
    # Run OLD method concurrently
    print(f"\nRunning {num_concurrent} concurrent calls with OLD method (pool size=3)...")
    start = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_concurrent) as executor:
        old_futures = [executor.submit(run_old_similarity, tc) for tc in test_cases_repeated]
        old_results = [f.result() for f in concurrent.futures.as_completed(old_futures)]
    old_concurrent_time = time.perf_counter() - start
    
    # Run NEW method concurrently
    print(f"Running {num_concurrent} concurrent calls with NEW method (semaphore=5)...")
    start = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_concurrent) as executor:
        new_futures = [executor.submit(run_new_similarity, tc) for tc in test_cases_repeated]
        new_results = [f.result() for f in concurrent.futures.as_completed(new_futures)]
    new_concurrent_time = time.perf_counter() - start
    
    print(f"\n{num_concurrent} calls OLD (pool): {old_concurrent_time*1000:.2f}ms")
    print(f"{num_concurrent} calls NEW (semaphore): {new_concurrent_time*1000:.2f}ms")
    if new_concurrent_time > 0:
        print(f"Concurrency improvement: {old_concurrent_time/new_concurrent_time:.2f}x faster")
    
    # Verify results are equivalent
    old_sorted = sorted(old_results)
    new_sorted = sorted(new_results)
    results_match = all(abs(o - n) < 1e-5 for o, n in zip(old_sorted, new_sorted))
    print(f"Results match: {'✅ YES' if results_match else '❌ NO'}")


if __name__ == "__main__":
    passed = run_tests()
    run_concurrent_test()
    
    exit(0 if passed else 1)
