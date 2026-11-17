"""Relay Cloudflare's encrypted edge connection through the host HTTP proxy.

Only loopback clients can connect. TLS remains between cloudflared and Cloudflare.
The public API and provider credentials are not inspected by this relay.
"""
import select
import socket
import socketserver
import urllib.parse
import urllib.request


class Edge(socketserver.BaseRequestHandler):
    def handle(self):
        proxy = urllib.parse.urlsplit(urllib.request.getproxies()['https'])
        with socket.create_connection((proxy.hostname, proxy.port), timeout=20) as upstream:
            target = 'region1.v2.argotunnel.com:7844'
            upstream.sendall(f'CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n'.encode())
            header = bytearray()
            while not header.endswith(b'\r\n\r\n'):
                chunk = upstream.recv(1)
                if not chunk or len(header) > 16384: return
                header.extend(chunk)
            if b' 200 ' not in header.split(b'\r\n')[0]: return
            upstream.settimeout(None)
            sockets = [self.request, upstream]
            while True:
                readable, _, _ = select.select(sockets, [], [], 60)
                for source in readable:
                    data = source.recv(65536)
                    if not data: return
                    (upstream if source is self.request else self.request).sendall(data)


if __name__ == '__main__':
    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True
    Server(('127.0.0.1', 8744), Edge).serve_forever()
