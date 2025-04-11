import httpx

REQUEST_TIMEOUT_SECONDS = 60

headers = { "User-Agent": "Mozilla/5.0" }  # Mimic a real browser

async def send_get_request(endpoint: str, headers: dict = None):
    async with httpx.AsyncClient(http2=True) as client:
        response = await client.get(endpoint, timeout=REQUEST_TIMEOUT_SECONDS, headers=headers )
        return response

async def send_post_request(endpoint: str, json_data, headers: dict = None):
    async with httpx.AsyncClient(http2=True) as client:
        response = await client.post(endpoint, json=json_data, timeout=REQUEST_TIMEOUT_SECONDS, headers=headers)
        return response
