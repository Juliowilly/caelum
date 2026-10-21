#!/usr/bin/env python3
"""
compass_bridge.py — polls PhyPhox magnetometer on the phone and
serves the heading as a plain float on localhost:8888/heading.

Usage:
    python3 compass_bridge.py [phyphox_url]
    default: http://192.168.1.140:8080

Set in tracker Settings → Phone compass URL:
    http://localhost:8888/heading
"""
import json, math, sys, threading, time, urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler

PHYPHOX  = (sys.argv[1] if len(sys.argv) > 1
            else 'http://192.168.1.140:8080')
API_URL  = PHYPHOX.rstrip('/') + '/get?magX&magY&magZ'
SERVE_PORT = 8888

_lock    = threading.Lock()
_state   = {'heading': None, 'last_ok': 0}

def _poll():
    while True:
        try:
            with urllib.request.urlopen(API_URL, timeout=2) as r:
                data = json.loads(r.read())
            buf  = data['buffer']
            x    = buf['magX']['buffer'][-1]
            y    = buf['magY']['buffer'][-1]
            # atan2(x, y): 0°=North, 90°=East — Redmi X axis is mirrored
            hdg  = (math.degrees(math.atan2(x, y)) + 360) % 360
            with _lock:
                _state['heading'] = hdg
                _state['last_ok'] = time.time()
        except Exception as e:
            pass
        time.sleep(0.5)

class _H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/heading':
            with _lock:
                h    = _state['heading']
                stale = time.time() - _state['last_ok'] > 5
            if h is None or stale:
                body = b'no data'; code = 503
            else:
                body = f'{h:.1f}'.encode(); code = 200
            self.send_response(code)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404); self.end_headers()
    def log_message(self, *_): pass

if __name__ == '__main__':
    print(f'Polling PhyPhox at {API_URL}')
    threading.Thread(target=_poll, daemon=True).start()
    time.sleep(1)
    with _lock:
        h = _state['heading']
    print(f'First reading: {h:.1f}°' if h else 'Waiting for data…')
    print(f'Serving heading at http://localhost:{SERVE_PORT}/heading')
    HTTPServer(('127.0.0.1', SERVE_PORT), _H).serve_forever()
