import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import unittest
from unittest.mock import patch
from urllib.request import Request

from certocr.local_http import open_local, validate_endpoint


class LocalHttpTests(unittest.TestCase):
    def test_credentials_and_remote_endpoints_rejected(self):
        for endpoint in ("http://user@127.0.0.1:9911", "http://127.0.0.1:11434",
                         "https://127.0.0.1:9911", "http://example.invalid:9911",
                         "http://127.0.0.1:9911/?redirect=1"):
            with self.assertRaises(ValueError):
                validate_endpoint(endpoint)

    def test_proxy_is_ignored_and_redirect_never_followed(self):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                if self.path == "/redirect":
                    self.send_response(302)
                    self.send_header("Location", "https://example.invalid/private")
                    self.end_headers()
                else:
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'{"local":true}')

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}"
            with patch.dict(os.environ, {"http_proxy": "http://127.0.0.1:1", "no_proxy": ""}):
                with open_local(Request(url), timeout=2) as response:
                    self.assertTrue(json.load(response)["local"])
                with self.assertRaises(ValueError):
                    open_local(Request(url + "/redirect"), timeout=2)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
