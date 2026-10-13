import http.server
import socketserver
import os
from pathlib import Path

PORT = 5173
DASHBOARD_DIR = Path(__file__).resolve().parent.parent / "apps" / "dashboard"

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DASHBOARD_DIR), **kwargs)

    def end_headers(self):
        # Enable CORS and caching headers for local dev
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        super().end_headers()

    def guess_type(self, path):
        if str(path).endswith(".js") or str(path).endswith(".ts"):
            return "application/javascript"
        return super().guess_type(path)

def run():
    print(f"CentrAlign Dashboard serving at http://localhost:{PORT}")
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nDashboard server stopped.")

if __name__ == "__main__":
    run()
