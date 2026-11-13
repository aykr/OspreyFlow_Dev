"""How many Postgres connections real Conduits hold once up, against a throwaway Postgres at a given
max_connections. ArcadeDB is a stand-in answering every command with an empty result (start-up asks it
first); Postgres is real. Prints the count after each Conduit and whether the next came up."""
import http.server, json, subprocess, sys, threading, time
import tests.services.api.test_statelessness as t

class A(http.server.BaseHTTPRequestHandler):
    def _r(self):
        n = int(self.headers.get("Content-Length") or 0); self.rfile.read(n)
        body = json.dumps({"result": ["ospreyflow"]} if "server" in self.path else {"result": []}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    do_GET = do_POST = _r
    def log_message(self, *a): pass

srv = http.server.ThreadingHTTPServer(("127.0.0.1", 59991), A)
threading.Thread(target=srv.serve_forever, daemon=True).start()

def held():
    out = subprocess.run(["/opt/homebrew/bin/psql", "-h", "127.0.0.1", "-p", "59992", "-U", "osprey", "-d", "postgres",
                          "-tAc", "SELECT count(*) FROM pg_stat_activity WHERE backend_type = 'client backend'"],
                         capture_output=True, text=True)
    return out.stdout.strip()

real = t._wait_until_up
t._wait_until_up = lambda url, **kw: real(url, **{**kw, "timeout_s": 60.0})
running = []
try:
    for n in (1, 2, 3):
        try:
            running.append(t._ConduitInstance("http://127.0.0.1:59995/jwks.json"))
            time.sleep(2)
            print(f"Conduit {n} up; client connections now held: {held()}", flush=True)
        except TimeoutError as exc:
            words = str(exc)
            print(f"Conduit {n} did NOT come up: {words.splitlines()[0][:120]}")
            print("  " + next((l for l in words.splitlines() if "TooManyConnections" in l or "too many" in l), "(no connection error in its words)")[:200])
            break
finally:
    for c in running:
        c.kill()
