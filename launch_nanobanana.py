"""
Launch Google Nano Banana AI Studio in your browser.
Uses Puter.js directly in the browser — 100% UI-based, zero API keys needed.
"""

import os
import sys
import webbrowser
from pathlib import Path
import http.server
import socketserver
import threading

PROJECT_ROOT = Path(__file__).resolve().parent
HTML_PATH = PROJECT_ROOT / "cloud_generator" / "web" / "nanobanana.html"

def main():
    if not HTML_PATH.exists():
        print(f"Error: {HTML_PATH} not found.")
        sys.exit(1)

    print("=" * 65)
    print("  🍌 GOOGLE NANO BANANA AI STUDIO (DIRECT BROWSER UI)")
    print("=" * 65)
    print("  • Engine: Google Gemini Vision via Puter.js")
    print("  • Mode: 100% UI-based (Client-Side, Zero API Keys Needed)")
    print("  • Models: Nano Banana 2, Nano Banana Pro, 2 Lite, Imagen 4.0")
    print("  • Frame: 9:16 Vertical Portrait (1080x1920), 1:1, 16:9")
    print("=" * 65)

    # Serve via lightweight local server to support browser origin policies
    port = 8765
    web_dir = PROJECT_ROOT / "cloud_generator" / "web"
    os.chdir(str(web_dir))

    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            pass  # quiet logs

    try:
        httpd = socketserver.TCPServer(("", port), Handler)
        url = f"http://localhost:{port}/nanobanana.html"
        print(f"\n🚀 Opening Studio in your browser: {url}")
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        webbrowser.open(url)
        print("💡 Press Ctrl+C in this terminal to stop the local server.\n")
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStudio closed.")
    except Exception as e:
        # Fallback to direct file URI
        file_url = HTML_PATH.as_uri()
        print(f"Opening file directly: {file_url}")
        webbrowser.open(file_url)

if __name__ == "__main__":
    main()
