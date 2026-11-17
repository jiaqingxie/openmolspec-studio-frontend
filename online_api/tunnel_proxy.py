"""Let cloudflared's provisioning request use this host's standard HTTPS proxy.

The upstream cloudflared quick-tunnel transport omits ProxyFromEnvironment.
Credentials pass only over loopback and stay in memory.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import urllib.request


class Proxy(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != '/tunnel':
            self.send_error(404); return
        payload = self.rfile.read(int(self.headers.get('Content-Length', '0')))
        request = urllib.request.Request('https://api.trycloudflare.com/tunnel', data=payload,
            headers={'User-Agent': self.headers.get('User-Agent', 'cloudflared'), 'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=40) as response:
            body = response.read(); self.send_response(response.status)
            self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(body)))
            self.end_headers(); self.wfile.write(body)

    def log_message(self, *args): pass


if __name__ == '__main__':
    ThreadingHTTPServer(('127.0.0.1', 8730), Proxy).serve_forever()
