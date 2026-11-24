"""Backend server using ONLY the Python standard library.
Run:  python server.py   then open http://localhost:8000"""
import json
import mimetypes
import os
import sqlite3
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from audit_lite import read_table, run_audit, sample_csv

BASE = Path(__file__).resolve().parent
SITE = BASE.parent / "frontend"
DB_PATH = BASE / "audits.db"
MAX_BYTES = 20 * 1024 * 1024
PORT = int(os.environ.get("PORT", 8000))          # hosts such as Render set PORT
HOST = "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1"


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


with db() as _c:
    _c.execute("""CREATE TABLE IF NOT EXISTS audits(
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, score INTEGER,
        created REAL, result TEXT, client TEXT)""")
    try:
        _c.execute("ALTER TABLE audits ADD COLUMN client TEXT")   # upgrade older databases
    except sqlite3.OperationalError:
        pass


class Handler(BaseHTTPRequestHandler):
    def send(self, status, body, ctype="application/json", extra=None):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def json(self, status, obj):
        self.send(status, json.dumps(obj), "application/json; charset=utf-8")

    def err(self, status, msg):
        self.json(status, {"detail": msg})

    def cid(self):
        return (self.headers.get("X-Client-Id") or "anon")[:64]

    def audit_id(self, path):
        try:
            return int(path.rsplit("/", 1)[1])
        except ValueError:
            return None

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/health":
            return self.json(200, {"status": "ok"})
        if path == "/api/sample":
            return self.send(200, sample_csv(), "text/csv; charset=utf-8",
                             {"Content-Disposition": "attachment; filename=loan_applications_sample.csv"})
        if path == "/api/audits":
            with db() as c:
                rows = c.execute("SELECT id,name,score,created FROM audits WHERE client=? ORDER BY id DESC LIMIT 100", (self.cid(),)).fetchall()
            return self.json(200, [dict(r) for r in rows])
        if path.startswith("/api/audits/"):
            aid = self.audit_id(path)
            with db() as c:
                row = c.execute("SELECT result FROM audits WHERE id=? AND client=?", (aid, self.cid())).fetchone()
            if not row:
                return self.err(404, "Audit not found.")
            res = json.loads(row["result"])
            res["id"] = aid
            return self.json(200, res)
        if path.startswith("/api/"):
            return self.err(404, "Unknown API route.")
        # static files
        rel = "index.html" if path in ("", "/") else path.lstrip("/")
        f = (SITE / rel).resolve()
        if SITE.resolve() not in f.parents or not f.is_file():
            return self.err(404, "Not found.")
        ctype = mimetypes.guess_type(str(f))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith("javascript"):
            ctype += "; charset=utf-8"
        self.send(200, f.read_bytes(), ctype)

    def do_POST(self):
        if urlparse(self.path).path != "/api/audit":
            return self.err(404, "Unknown API route.")
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BYTES:
            return self.err(413, "File is larger than 20 MB.")
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
            head, rows = read_table(str(body.get("csv", "")).encode("utf-8"))
            attrs = body.get("attrs")
            if attrs is not None and not isinstance(attrs, list):
                raise ValueError("attrs must be a list of column names.")
            result = run_audit(head, rows, body.get("name") or "dataset.csv",
                               body.get("outcome") or None, body.get("favourable") or None, attrs)
        except json.JSONDecodeError:
            return self.err(400, "Request body must be JSON.")
        except ValueError as exc:
            return self.err(400, str(exc))
        with db() as c:
            cur = c.execute("INSERT INTO audits(name,score,created,result,client) VALUES(?,?,?,?,?)",
                            (result["name"], result["score"], time.time(), json.dumps(result), self.cid()))
            result["id"] = cur.lastrowid
        self.json(200, result)

    def do_DELETE(self):
        path = urlparse(self.path).path
        if not path.startswith("/api/audits/"):
            return self.err(404, "Unknown API route.")
        aid = self.audit_id(path)
        with db() as c:
            c.execute("DELETE FROM audits WHERE id=? AND client=?", (aid, self.cid()))
        self.json(200, {"deleted": aid})


if __name__ == "__main__":
    try:
        server = ThreadingHTTPServer((HOST, PORT), Handler)
    except OSError:
        raise SystemExit(f"Port {PORT} is already in use. Close the other server (Ctrl+C) and try again.")
    print(f"AI Bias Detector running on port {PORT}  (local: http://localhost:{PORT}, press Ctrl+C to stop)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
