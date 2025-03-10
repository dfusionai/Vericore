import time
import random

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from dataclasses import asdict



###############################################################################
# Set up FastAPI server
###############################################################################

@asynccontextmanager
async def lifespan(app: FastAPI):
    await startup_event()
    yield  # This keeps the app running

app = FastAPI(title="Veridex API Server", lifespan=lifespan)

origins = [
    "*",
]

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # Allowed origins
    allow_credentials=True,  # Allow sending cookies (useful for auth)
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
)

# Create the APIQueryHandler during startup and store it in app.state.
async def startup_event():
    print('startup_event')
    print("APIQueryHandler instance created at startup.")

@app.post("")
async def log(request: Request):
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    statement = data.get("statement")
    sources = data.get("sources", [])
    if not statement:
        raise HTTPException(status_code=400, detail="Missing 'statement'")
    request_id = f"req-{random.getrandbits(32):08x}"
    handler = app.state.handler
    start_time = time.time()
    result = await handler.handle_query(request_id, statement, sources)
    end_time = time.time()
    print(f"{request_id} | Finished processing at {end_time} (Duration: {end_time - start_time})")
    return JSONResponse(asdict(result))

if __name__ == "__main__":
    import uvicorn

    # Run uvicorn with one worker to ensure a single instance of APIQueryHandler.
    uvicorn.run("validator.api_server:app", host="0.0.0.0", port=8080, reload=False, timeout_keep_alive=500)
