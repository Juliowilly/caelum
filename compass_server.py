import subprocess, math, json
from http.server import HTTPServer, BaseHTTPRequestHandler

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            raw = subprocess.run(
                ['termux-sensor', '-s', 'Magnetic Field', '-n', '1', '-d', '200'],
                capture_output=True, text=True, timeout=5).stdout
            v = json.loads(raw)['Magnetic Field']['values']
            hdg = (math.degrees(math.atan2(v[1], v[0])) + 360) % 360
            body = f'{hdg:.1f}'.encode()
            self.send_response(200)
        except Exception as e:
            body = str(e).encode()
            self.send_response(500)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass

print('Compass server on :5006')
HTTPServer(('0.0.0.0', 5006), H).serve_forever()
