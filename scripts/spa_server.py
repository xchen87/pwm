"""Serve a built single-page app: real files as they are, every other path as index.html,
so a deep link such as /auth?code=... reaches the app. Test tooling only.

Usage: python scripts/spa_server.py <directory> <port>
"""

import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class SpaHandler(SimpleHTTPRequestHandler):
    def send_head(self):  # type: ignore[no-untyped-def]
        requested = Path(self.translate_path(self.path))
        if not requested.exists():
            self.path = "/index.html"
        return super().send_head()

    def log_message(self, *args: object) -> None:
        pass


if __name__ == "__main__":
    directory, port = sys.argv[1], int(sys.argv[2])
    handler = partial(SpaHandler, directory=directory)
    ThreadingHTTPServer(("127.0.0.1", port), handler).serve_forever()
