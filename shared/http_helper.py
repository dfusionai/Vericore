import datetime
import bittensor as bt
import httpx
# import asyncio

REQUEST_TIMEOUT_SECONDS = 60

async def log_request(request):
    bt.logging.info(f"{datetime.datetime.now()} | {request.method} {request.url} ")

async def log_response(response):
    request = response.request
    bt.logging.info(f"{datetime.datetime.now()} | {request.method} {request.url} | STATUS CODE: {response.status_code}")

async def send_get_request(endpoint: str, headers: dict = None):
    async with httpx.AsyncClient(http2=True) as client:
        client.event_hooks['request'] = [log_request]
        client.event_hooks['response'] = [log_response]
        response = await client.get(endpoint, timeout=REQUEST_TIMEOUT_SECONDS, headers=headers )
        return response

async def send_post_request(endpoint: str, json_data, headers: dict = None):
    async with httpx.AsyncClient(http2=True) as client:
        client.event_hooks['request'] = [log_request]
        client.event_hooks['response'] = [log_response]
        response = await client.post(endpoint, json=json_data, timeout=REQUEST_TIMEOUT_SECONDS, headers=headers)
        return response

# headers = { "User-Agent": "Mozilla/5.0" }
#
# async def main():
#     await send_get_request('https://medium.com/@georgexwee/concurrency-in-python-multi-threading-c3fab37737c')
#     await send_get_request('https://shazaali.substack.com/p/webhooks-and-multithreading-in-python')
#     await send_get_request('https://medium.com/@akshaybagal/boosting-api-data-retrieval-and-processing-with-multithreading-best-practices-and-sample-code-fc5d1396ade9')
#
#
# if __name__ == "__main__":
#     asyncio.run(main())

