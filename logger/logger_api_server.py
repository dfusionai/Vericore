import json
import os
import boto3
import time
import argparse

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

import bittensor as bt
from shared.log_data import LogEntry

from dotenv import load_dotenv

# debug
load_dotenv()

REFRESH_INTERVAL_SECONDS = 90

###############################################################################
# Aws Config Values (Should get from environment
###############################################################################

LOG_GROUP_NAME = "Vericore"  # Change this
LOG_STREAM_NAME = "Logs"  # Change this

###############################################################################
# LogHandler: processes the json to send to Aws Cloud Watch
###############################################################################
class LogHandler:
    def __init__(self):
        # Load Perplexity AI key
        aws_region_name = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
        aws_access_key_id = os.environ.get("AWS_ACCESS_KEY_ID", "YOUR_API_KEY_HERE")
        aws_secret_access_key = os.environ.get("AWS_SECRET_ACCESS_KEY", "YOUR_API_KEY_HERE")

        if not aws_access_key_id or aws_access_key_id.startswith("YOUR_API_KEY_HERE"):
            bt.logging.warning("No AWS_ACCESS_KEY_ID found. Please set it to use AWS.")

        if not aws_secret_access_key or aws_secret_access_key.startswith("YOUR_API_KEY_HERE"):
            bt.logging.warning("No AWS_ACCESS_KEY_ID found. Please set it to use AWS.")

        aws_session = boto3.Session(
            region_name=aws_region_name,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key
        )
        self.aws_log_client = aws_session.client(
            "logs",
        )

        # Create Log Group (if not exists)
        try:
            self.aws_log_client.create_log_group(logGroupName=LOG_GROUP_NAME)
        except self.aws_log_client.exceptions.ClientError as e:
            if e.response['Error']['Code'] == 'ResourceAlreadyExistsException':
                print("Log group already exists")
            else:
                raise

        # Create Log Stream (if not exists)
        try:
          self.aws_log_client.create_log_stream(logGroupName=LOG_GROUP_NAME, logStreamName=LOG_STREAM_NAME)
        except self.aws_log_client.exceptions.ClientError as e:
          if e.response['Error']['Code'] == 'ResourceAlreadyExistsException':
              print("Log stream already exists")
          else:
              raise

        # Get config from arguments passed
        self.last_refresh_time = 0  # Timestamp of the last sync

        self.config = self.get_config()
        print(f"Fetched and configured config")
        self.subtensor = bt.subtensor(config=self.config)
        print(f"Subtensor: {self.subtensor}")
        # fetch metagraph object for validating wallets
        self.metagraph = self.subtensor.metagraph(self.config.netuid)
        print(f"Metagraph: {self.metagraph}")

    def get_config(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("--custom", default="my_custom_value", help="Custom value")
        parser.add_argument("--netuid", type=int, default=1, help="Chain subnet uid")
        bt.subtensor.add_args(parser)
        return bt.config(parser)

    def refresh_metagraph(self):
        current_time = time.time()
        if  (current_time - self.last_refresh_time) > REFRESH_INTERVAL_SECONDS:
            print("Refreshing metagraph")
            self.metagraph.sync()  # Fetch new data

    def verify_request(self, request: Request, log_entry: LogEntry):
        if not request.headers.get("wallet"):
            raise HTTPException(status_code=401, detail="Invalid wallet")

        if not request.headers.get("signature"):
            raise HTTPException(status_code=401, detail="Invalid signature")

        wallet_hotkey = request.headers.get("wallet")
        signature = request.headers.get("signature")

        #refresh metagraph
        self.refresh_metagraph()
        # check to see whether wallet hotkey is valid within the bittensor network
        if not wallet_hotkey in self.metagraph.hotkeys:
            raise HTTPException(status_code=401, detail="Invalid wallet hotkey")

        # create message
        message = f"{log_entry.level}.{log_entry.timestamp}.{wallet_hotkey}.log"
        message_bytes = message.encode("utf-8")
        signature_bytes = bytes.fromhex(signature)

        hotkey = bt.Keypair(ss58_address=wallet_hotkey)
        verified = hotkey.verify(message_bytes, signature_bytes)

        print(f"Verified: {verified}")

        if not verified:
            raise HTTPException(status_code=401, detail="Unauthorized signature")

    def sendLogEvent(self, log_entry: LogEntry):
        aws_log_event = {
            # "sequenceToken": sequence_token,
            "logGroupName": LOG_GROUP_NAME,
            "logStreamName": LOG_STREAM_NAME,
            "logEvents": [
                {
                    "timestamp": int(log_entry.timestamp * 1000), # convert to milliseconds
                    "message": log_entry.message, # we can dump entire object
                }
            ],
        }
        # Send log entry
        try:
            response = self.aws_log_client.put_log_events(**aws_log_event)
            print(f"Log sent successfully: {response["nextSequenceToken"]}")
        except Exception as e:
            print(f"Error sending log entry: {e}")

    def logEvent(self, log_entry: LogEntry):
        self.sendLogEvent(log_entry)


###############################################################################
# Set up FastAPI server
###############################################################################

@asynccontextmanager
async def lifespan(app: FastAPI):
    await startup_event()
    yield  # This keeps the app running

app = FastAPI(title="Vericore Logger API Server", lifespan=lifespan)

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
    app.state.handler = LogHandler()
    print("LogHandler instance created at startup.")


@app.post("/log")
async def log(request: Request):
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    json_data = json.loads(data)

    log_entry = LogEntry(**json_data)
    if not log_entry:
        raise HTTPException(status_code=400, detail="Invalid Log Entry")

    handler = app.state.handler

    handler.verify_request(request, log_entry)

    handler.logEvent(log_entry)

    print(f"Sent log")

    return JSONResponse('done')

if __name__ == "__main__":
    import uvicorn

    # Run uvicorn with one worker to ensure a single instance of APIQueryHandler.
    uvicorn.run("logger.logger_api_server:app", host="0.0.0.0", port=8086, reload=False, timeout_keep_alive=500)
