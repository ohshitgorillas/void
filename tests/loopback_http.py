# HTTP servers for tests that bind to 127.0.0.1 without http.server's name lookup. HTTPServer.server_bind calls
# socket.getfqdn(host) after the bind, and on the macos-15 runner that blocks about 35 s in mdns_hostbyaddr. Everything
# else is http.server's, so a port another process holds still fails at bind. Stdlib only and nothing runs at import:
# the child-process fakes carry this file's text as the head of their script, since the launchers run them with no path
# back to tests/.
import socketserver
from http.server import HTTPServer, ThreadingHTTPServer


class _NoLookup:
    def server_bind(self):
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


class LoopbackHTTPServer(_NoLookup, HTTPServer):
    pass


class LoopbackThreadingHTTPServer(_NoLookup, ThreadingHTTPServer):
    pass
