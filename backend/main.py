import asyncio
import json
import logging
import pathlib
import os
import queue
from multiprocessing import Process, Queue

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from mitmproxy.tools.dump import DumpMaster
from mitmproxy.options import Options

from copilot_logger import CopilotLogger

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = pathlib.Path(os.path.expanduser("~/.mitmproxy/intercepter_vscode/copilot_mitm"))
EVENTS_PATH = BASE_DIR / "events.jsonl"
BASE_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI()
event_queue = Queue()
mitm_process: Process | None = None

# Add CORS middleware to allow requests from your frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

def run_mitmproxy(queue_instance: Queue):
    """Runs mitmproxy's DumpMaster in a separate process."""
    
    def on_event_callback(event_data):
        """Callback to put event data (as a dictionary) into the shared queue without blocking."""
        try:
            queue_instance.put_nowait(event_data)
        except queue.Full:
            logger.warning("Event queue is full. An event from mitmproxy was dropped.")

    async def start_proxy():
        opts = Options()
        opts.listen_host = '0.0.0.0'
        opts.listen_port = 8080
        opts.allow_hosts = [".*githubcopilot\\.com"]
        
        master = DumpMaster(opts)
        # Pass the callback to the logger addon
        master.addons.add(CopilotLogger(on_event_callback=on_event_callback))
        logger.info("mitmproxy is starting on port 8080")
        await master.run()

    asyncio.run(start_proxy())

@app.on_event("startup")
async def startup_event():
    """Start the mitmproxy process on server startup."""
    global mitm_process
    mitm_process = Process(target=run_mitmproxy, args=(event_queue,))
    mitm_process.start()
    logger.info("mitmproxy process started.")

@app.on_event("shutdown")
async def shutdown_event():
    """Stop the mitmproxy process on server shutdown."""
    global mitm_process
    if mitm_process and mitm_process.is_alive():
        logger.info("Terminating mitmproxy process.")
        mitm_process.terminate()
        mitm_process.join()
        logger.info("mitmproxy process terminated.")

@app.get("/history", response_model=list[dict])
async def get_history():
    """Reads and returns all historical events from the events.jsonl file."""
    if not EVENTS_PATH.exists():
        return []
    
    events = []
    try:
        with open(EVENTS_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        logger.warning(f"Skipping malformed line in events.jsonl: {line.strip()}")
        return events
    except Exception as e:
        logger.error(f"Error reading history file: {e}")
        return JSONResponse(content={"error": "Could not read history file"}, status_code=500)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Handles WebSocket connections and pushes data from the queue."""
    await websocket.accept()
    logger.info("Frontend connected via WebSocket.")
    try:
        while True:
            if not event_queue.empty():
                # Get the event dictionary from the queue
                event_dict = event_queue.get()
                
                # The logger now handles file writing. We just send to the client.
                event_json_str = json.dumps(event_dict, ensure_ascii=False)
                await websocket.send_text(event_json_str)

            await asyncio.sleep(0.1) # Prevent busy-waiting
    except WebSocketDisconnect:
        logger.info("Frontend disconnected.")
    except Exception as e:
        logger.error(f"WebSocket Error: {e}")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, lifespan="on", loop="asyncio")