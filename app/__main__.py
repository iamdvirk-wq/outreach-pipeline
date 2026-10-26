"""Start the dashboard: python -m app (start.sh / start.bat do this for you)."""
import os
import threading
import webbrowser

import uvicorn

from app import config

if __name__ == "__main__":
    url = f"http://localhost:{config.PORT}"
    print(f"\n  Outreach dashboard: {url}")
    print("  Keep this window open while you use it. Press Ctrl+C to stop.\n")
    if os.getenv("NO_BROWSER") != "1":
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run("app.main:app", host=config.HOST, port=config.PORT, log_level="warning")
