import asyncio
import json
import logging
import pathlib
import os
from multiprocessing import Process, Queue

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
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

def run_mitmproxy(queue: Queue):
    """Runs mitmproxy's DumpMaster in a separate process."""
    
    def on_event_callback(event_data):
        """Callback to put event data (as a dictionary) into the shared queue."""
        queue.put(event_data)

    async def start_proxy():
        opts = Options()
        opts.listen_host = '0.0.0.0'
        opts.listen_port = 8080
        opts.web_host = '' 
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
    mitm_process = Process(target=run_mitmproxy, args=(event_queue,))
    mitm_process.start()
    logger.info("mitmproxy process started.")

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
                event_json_str = json.dumps(event_dict, ensure_ascii=False)

                with open(EVENTS_PATH, "a", encoding="utf-8") as f:
                    f.write(event_json_str + "\n")

                # Send to the WebSocket for real-time display
                await websocket.send_text(event_json_str)
                

            await asyncio.sleep(0.1) # Prevent busy-waiting
    except WebSocketDisconnect:
        logger.info("Frontend disconnected.")
    except Exception as e:
        logger.error(f"WebSocket Error: {e}")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)