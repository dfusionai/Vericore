# filename: http_clients_with_args.py
import asyncio
import requests
import httpx
import time
import sys


def fetch_with_requests(url):
    start = time.perf_counter()
    try:
        response = requests.get(url)
        response.raise_for_status()
        duration = time.perf_counter() - start
        print(f"[requests] Status: {response.status_code} | Time: {duration:.4f} seconds")
        return response.text
    except requests.RequestException as e:
        duration = time.perf_counter() - start
        print(f"[requests] Error: {e} | Time: {duration:.4f} seconds")
        return None


def fetch_with_httpx(url):
    start = time.perf_counter()
    try:
        with httpx.Client() as client:
            response = client.get(url)
            response.raise_for_status()
            duration = time.perf_counter() - start
            print(f"[httpx] Status: {response.status_code} | Time: {duration:.4f} seconds")
            return response.text
    except httpx.RequestError as e:
        duration = time.perf_counter() - start
        print(f"[httpx] Error: {e} | Time: {duration:.4f} seconds")
        return None

async def fetch_with_httpx_async(url):
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(
            http2=True,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept-Encoding": "gzip, deflate"
            },
            timeout=60.0
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            duration = time.perf_counter() - start
            print(f"[httpx-async] Status: {response.status_code} | Time: {duration:.4f} seconds")
            return response.text
    except httpx.RequestError as e:
        duration = time.perf_counter() - start
        print(f"[httpx-async] Error: {e} | Time: {duration:.4f} seconds")
        return None

if __name__ == "__main__":
    test_url = "https://httpbin.org/get"
    url = sys.argv[1] if len(sys.argv) > 1 else test_url

    print(f"\nTarget URL: {url}")

    print("\n--- Using requests ---")
    fetch_with_requests(url)

    print("\n--- Using httpx ---")
    fetch_with_httpx(url)

    print("\n--- Using httpx.AsyncClient (HTTP/2) ---")
    asyncio.run(fetch_with_httpx_async(url))

