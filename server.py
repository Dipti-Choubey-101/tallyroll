#!/usr/bin/env python3
"""
Tallyroll - a private receipt and supplier-bill sorter for small restaurants.

Everything runs on this computer:
  * the web page you see is served from here (127.0.0.1 only, nobody else on the network can reach it)
  * the bills are read by Gemma, an open-weight model, running inside Ollama on this computer
  * the results are saved in the "data" folder next to this file

Uses only the Python standard library. (Pillow is optional: if installed it
straightens and shrinks photos before reading, which is faster and more accurate.)
"""
import base64
import csv
import io
import json
import mimetypes
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import webbrowser
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    from PIL import Image, ImageOps  # optional
    HAVE_PIL = True
except Exception:  # pragma: no cover
    HAVE_PIL = False

ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(ROOT, "static")
SAMPLES = os.path.join(ROOT, "sample-receipts")
DATA = os.environ.get("TALLYROLL_DATA", os.path.join(ROOT, "data"))
IMAGES = os.path.join(DATA, "images")
DB_FILE = os.path.join(DATA, "receipts.json")
SETTINGS_FILE = os.path.join(DATA, "settings.json")
os.makedirs(IMAGES, exist_ok=True)

LOCK = threading.Lock()

CATEGORIES = [
    {"id": "produce",    "name": "Vegetables & fruit",   "color": "#4f9a5f"},
    {"id": "meat",       "name": "Meat, fish & eggs",    "color": "#c8503c"},
    {"id": "dairy",      "name": "Dairy",                "color": "#e0b94a"},
    {"id": "grocery",    "name": "Dry goods & spices",   "color": "#b9803f"},
    {"id": "drinks",     "name": "Drinks",               "color": "#3e8fb0"},
    {"id": "packaging",  "name": "Packaging & takeaway", "color": "#7b6bb0"},
    {"id": "gas",        "name": "Gas & fuel",           "color": "#e0742f"},
    {"id": "utilities",  "name": "Electricity, water & internet", "color": "#2f6f8a"},
    {"id": "rent",       "name": "Rent",                 "color": "#6c7a74"},
    {"id": "staff",      "name": "Staff & wages",        "color": "#a05c8a"},
    {"id": "repairs",    "name": "Equipment & repairs",  "color": "#8a8f3c"},
    {"id": "cleaning",   "name": "Cleaning & supplies",  "color": "#4aa6a0"},
    {"id": "marketing",  "name": "Marketing & delivery apps", "color": "#d2688c"},
    {"id": "licences",   "name": "Licences & fees",      "color": "#7d8590"},
    {"id": "other",      "name": "Other",                "color": "#9aa39e"},
]
CATEGORY_IDS = [c["id"] for c in CATEGORIES]

DEFAULT_SETTINGS = {
    "model": "gemma3:4b",
    "ollama_url": "http://127.0.0.1:11434",
    "currency": "INR",
    "demo": False,
    "day_first": True,
}

# --------------------------------------------------------------------------
# Small JSON "database"
# --------------------------------------------------------------------------

def _read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def load_settings():
    s = dict(DEFAULT_SETTINGS)
    s.update(_read_json(SETTINGS_FILE, {}))
    return s


def save_settings(new):
    s = load_settings()
    for k in DEFAULT_SETTINGS:
        if k in new:
            s[k] = new[k]
    s["model"] = str(s["model"]).strip() or DEFAULT_SETTINGS["model"]
    s["ollama_url"] = str(s["ollama_url"]).strip().rstrip("/") or DEFAULT_SETTINGS["ollama_url"]
    s["currency"] = str(s["currency"]).strip().upper()[:3] or "INR"
    s["demo"] = bool(s["demo"])
    s["day_first"] = bool(s["day_first"])
    _write_json(SETTINGS_FILE, s)
    return s


def load_receipts():
    return _read_json(DB_FILE, [])


def save_receipts(rows):
    _write_json(DB_FILE, rows)

# --------------------------------------------------------------------------
# Cleaning up what the model returns
# --------------------------------------------------------------------------

CURRENCY_SYMBOLS = {"₹": "INR", "rs": "INR", "rs.": "INR", "inr": "INR", "$": "USD", "usd": "USD",
                    "€": "EUR", "eur": "EUR", "£": "GBP", "gbp": "GBP", "aed": "AED", "sgd": "SGD"}


def to_number(v):
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return round(float(v), 2)
    m = re.search(r"-?\d[\d.,]*", str(v))
    if not m:
        return None
    s = m.group(0).rstrip(".,")
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):      # 1.234,50  (European)
            s = s.replace(".", "").replace(",", ".")
        else:                                # 1,234.50
            s = s.replace(",", "")
    elif "," in s:
        # "1,234" -> thousands ; "12,50" -> decimal
        s = s.replace(",", "") if re.search(r",\d{3}(?!\d)", s) else s.replace(",", ".")
    try:
        return round(float(s), 2)
    except ValueError:
        return None


MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


def to_iso_date(v, day_first=True):
    if not v:
        return ""
    s = str(v).strip().lower()
    m = re.search(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", s)
    if m:
        y, mo, d = int(m[1]), int(m[2]), int(m[3])
        return _safe_date(y, mo, d)
    m = re.search(r"(\d{1,2})[-/.\s]+([a-z]{3})[a-z]*[-/.,\s]+(\d{2,4})", s)
    if m and m[2] in MONTHS:
        y = int(m[3]); y += 2000 if y < 100 else 0
        return _safe_date(y, MONTHS[m[2]], int(m[1]))
    m = re.search(r"([a-z]{3})[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})", s)
    if m and m[1] in MONTHS:
        return _safe_date(int(m[3]), MONTHS[m[1]], int(m[2]))
    m = re.search(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})", s)
    if m:
        a, b, y = int(m[1]), int(m[2]), int(m[3]); y += 2000 if y < 100 else 0
        d, mo = (a, b) if day_first else (b, a)
        if mo > 12 and d <= 12:
            d, mo = mo, d
        return _safe_date(y, mo, d)
    return ""


def _safe_date(y, m, d):
    try:
        return date(y, m, d).isoformat()
    except ValueError:
        return ""


def pick_currency(v, fallback):
    if not v:
        return fallback
    s = str(v).strip().lower()
    if s in CURRENCY_SYMBOLS:
        return CURRENCY_SYMBOLS[s]
    if re.fullmatch(r"[a-z]{3}", s):
        return s.upper()
    for sym, code in CURRENCY_SYMBOLS.items():
        if sym in s and not sym.isalpha():
            return code
    return fallback


def normalise(raw, settings, filename):
    """Turn whatever the model said into a clean, predictable record."""
    items = []
    for it in (raw.get("items") or [])[:60]:
        if isinstance(it, dict) and it.get("name"):
            items.append({"name": str(it["name"])[:80], "amount": to_number(it.get("amount"))})
    cat = str(raw.get("category", "other")).strip().lower()
    if cat not in CATEGORY_IDS:
        cat = "other"
    conf = str(raw.get("confidence", "medium")).lower()
    if conf not in ("high", "medium", "low"):
        conf = "medium"
    rec = {
        "vendor": str(raw.get("vendor") or "").strip()[:80],
        "date": to_iso_date(raw.get("date"), settings["day_first"]),
        "total": to_number(raw.get("total")),
        "tax": to_number(raw.get("tax")),
        "currency": pick_currency(raw.get("currency"), settings["currency"]),
        "category": cat,
        "payment": str(raw.get("payment_method") or "").strip()[:30],
        "items": items,
        "notes": str(raw.get("notes") or "").strip()[:240],
        "confidence": conf,
    }
    problems = []
    if not rec["vendor"]:
        problems.append("vendor missing")
    if not rec["date"]:
        problems.append("date missing")
    if rec["total"] is None:
        problems.append("total missing")
    priced = [i["amount"] for i in items if i["amount"] is not None]
    if rec["total"] and priced and len(priced) == len(items):
        s = sum(priced)
        if abs(s - rec["total"]) > max(2.0, 0.12 * rec["total"]) and abs(s + (rec["tax"] or 0) - rec["total"]) > max(2.0, 0.12 * rec["total"]):
            problems.append("line items do not add up to the total")
    if conf == "low":
        problems.append("hard to read")
    rec["problems"] = problems
    rec["status"] = "review" if problems else "ok"
    return rec

# --------------------------------------------------------------------------
# Talking to Gemma through Ollama
# --------------------------------------------------------------------------

SCHEMA = {
    "type": "object",
    "properties": {
        "vendor": {"type": "string"},
        "date": {"type": "string"},
        "total": {"type": "number"},
        "tax": {"type": "number"},
        "currency": {"type": "string"},
        "category": {"type": "string", "enum": CATEGORY_IDS},
        "payment_method": {"type": "string"},
        "items": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "amount": {"type": "number"}}, "required": ["name"]}},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "notes": {"type": "string"},
    },
    "required": ["vendor", "date", "total", "category", "confidence"],
}


def build_prompt(settings):
    cats = "\n".join("- %s: %s" % (c["id"], c["name"]) for c in CATEGORIES)
    return (
        "You are the bookkeeper for a small restaurant. The image is a photo or scan of ONE bill, "
        "receipt or supplier invoice. Read it carefully and return a JSON object.\n\n"
        "Rules:\n"
        "- vendor: the shop or company that issued the bill (not the restaurant that received it).\n"
        "- date: the bill date written as YYYY-MM-DD. If the day and month are ambiguous, assume %s.\n"
        "- total: the final amount to be paid, as a plain number (no currency symbol, no commas).\n"
        "- tax: total GST / VAT / tax on the bill as a plain number, 0 if none is shown.\n"
        "- currency: 3-letter code. Use %s if the bill shows no clear currency.\n"
        "- payment_method: cash, card, UPI, bank transfer, credit, or empty if not shown.\n"
        "- items: up to 30 main line items with the name and the line amount. Skip if unreadable.\n"
        "- category: pick the single best id from this list:\n%s\n"
        "- confidence: high if every key number is clearly legible, medium if you had to guess one thing, low if the image is blurry or cut off.\n"
        "- notes: one short sentence only if something is odd (handwritten, cut off, missing total). Otherwise empty.\n"
        "Never invent numbers. If something is not on the bill, leave it empty or 0.\n"
        "Return only the JSON object."
    ) % ("day before month" if settings["day_first"] else "month before day", settings["currency"], cats)


class ModelError(Exception):
    pass


def ollama_json(settings, path, payload=None, timeout=5):
    url = settings["ollama_url"] + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def read_with_gemma(settings, image_bytes):
    payload = {
        "model": settings["model"],
        "stream": False,
        "format": SCHEMA,
        "options": {"temperature": 0, "num_ctx": 4096},
        "messages": [{"role": "user", "content": build_prompt(settings),
                      "images": [base64.b64encode(image_bytes).decode("ascii")]}],
    }
    try:
        res = ollama_json(settings, "/api/chat", payload, timeout=900)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        if e.code == 404 or "not found" in body.lower():
            raise ModelError("The model '%s' is not installed yet. Double-click setup-model.bat, then try again." % settings["model"])
        raise ModelError("Ollama said: %s" % body[:200])
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
        raise ModelError("Cannot reach Ollama. Open the Ollama app (look for the llama icon in the taskbar), then try again.")
    text = (res.get("message") or {}).get("content", "")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise ModelError("The model answered, but not in a form Tallyroll could read. Try again.")
        try:
            parsed = json.loads(m.group(0))
        except json.JSONDecodeError:
            raise ModelError("The model answered, but not in a form Tallyroll could read. Try again.")
    return parsed, {"tokens": res.get("eval_count"), "model_ms": int((res.get("total_duration") or 0) / 1e6)}

# Demo mode: only knows the bundled sample bills, and is always labelled "demo".

def read_demo(filename):
    table = _read_json(os.path.join(SAMPLES, "samples.json"), {})
    base = os.path.basename(filename or "")
    if base not in table:
        raise ModelError("Demo mode only knows the sample bills. Turn demo mode off in Settings to read your own.")
    time.sleep(1.4)
    return dict(table[base]), {"tokens": None, "model_ms": 1400}

# --------------------------------------------------------------------------
# Images
# --------------------------------------------------------------------------

def sniff_image(b):
    if b[:3] == b"\xff\xd8\xff":
        return "jpg"
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "webp"
    if b[:4] == b"%PDF":
        return "pdf"
    return None


def prepare_image(b, ext):
    """Straighten phone photos and shrink them. Falls back to the original bytes."""
    if not HAVE_PIL:
        return b, ext
    try:
        im = Image.open(io.BytesIO(b))
        im = ImageOps.exif_transpose(im)
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        im.thumbnail((1600, 1600))
        out = io.BytesIO()
        im.save(out, "JPEG", quality=88)
        return out.getvalue(), "jpg"
    except Exception:
        return b, ext

# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

EDITABLE = {"vendor", "date", "total", "tax", "currency", "category", "payment", "notes", "items"}


class Handler(BaseHTTPRequestHandler):
    server_version = "Tallyroll/1.0"

    def log_message(self, fmt, *args):
        pass  # keep the console quiet

    # -- helpers
    def send_json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path, download_name=None):
        if not os.path.isfile(path):
            return self.send_json({"error": "Not found"}, 404)
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        with open(path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def body(self, limit=40 * 1024 * 1024):
        n = int(self.headers.get("Content-Length") or 0)
        if n > limit:
            raise ValueError("File is too large")
        return self.rfile.read(n)

    def same_origin(self):
        # Stop other websites from poking at the local server.
        origin = self.headers.get("Origin")
        if not origin:
            return True
        host = self.headers.get("Host", "")
        return urllib.parse.urlparse(origin).netloc == host

    # -- routes
    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        p, q = u.path, urllib.parse.parse_qs(u.query)
        if p == "/api/config":
            return self.send_json({"categories": CATEGORIES, "pillow": HAVE_PIL, "settings": load_settings()})
        if p == "/api/status":
            return self.send_json(self.status())
        if p == "/api/receipts":
            with LOCK:
                return self.send_json(load_receipts())
        if p.startswith("/api/image/"):
            rid = os.path.basename(p)
            with LOCK:
                row = next((r for r in load_receipts() if r["id"] == rid), None)
            if not row:
                return self.send_json({"error": "Not found"}, 404)
            return self.send_file(os.path.join(IMAGES, rid + "." + row["image_ext"]))
        if p == "/api/samples":
            names = sorted(f for f in os.listdir(SAMPLES) if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")))
            return self.send_json(names)
        if p.startswith("/samples/"):
            return self.send_file(os.path.join(SAMPLES, os.path.basename(p)))
        if p == "/api/export.csv":
            return self.export_csv(q.get("month", [""])[0])
        # static
        if p == "/":
            p = "/index.html"
        full = os.path.normpath(os.path.join(STATIC, p.lstrip("/")))
        if not full.startswith(STATIC):
            return self.send_json({"error": "Not found"}, 404)
        return self.send_file(full)

    def do_POST(self):
        if not self.same_origin():
            return self.send_json({"error": "Blocked"}, 403)
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        if u.path == "/api/scan":
            return self.scan(urllib.parse.unquote(q.get("filename", ["bill"])[0]))
        if u.path == "/api/settings":
            try:
                new = json.loads(self.body(1_000_000) or b"{}")
            except ValueError:
                return self.send_json({"error": "Bad request"}, 400)
            with LOCK:
                return self.send_json(save_settings(new))
        if u.path == "/api/clear":
            with LOCK:
                for f in os.listdir(IMAGES):
                    try:
                        os.remove(os.path.join(IMAGES, f))
                    except OSError:
                        pass
                save_receipts([])
            return self.send_json({"ok": True})
        return self.send_json({"error": "Not found"}, 404)

    def do_PATCH(self):
        if not self.same_origin():
            return self.send_json({"error": "Blocked"}, 403)
        rid = os.path.basename(urllib.parse.urlparse(self.path).path)
        try:
            patch = json.loads(self.body(1_000_000) or b"{}")
        except ValueError:
            return self.send_json({"error": "Bad request"}, 400)
        with LOCK:
            rows = load_receipts()
            row = next((r for r in rows if r["id"] == rid), None)
            if not row:
                return self.send_json({"error": "Not found"}, 404)
            for k, v in patch.items():
                if k not in EDITABLE:
                    continue
                if k in ("total", "tax"):
                    v = to_number(v)
                elif k == "date":
                    v = to_iso_date(v) or ""
                elif k == "category":
                    v = v if v in CATEGORY_IDS else "other"
                elif k == "items":
                    v = [{"name": str(i.get("name", ""))[:80], "amount": to_number(i.get("amount"))}
                         for i in v if isinstance(i, dict) and i.get("name")]
                else:
                    v = str(v)[:240]
                row[k] = v
            row["edited"] = True
            row["problems"] = [x for x in (
                "vendor missing" if not row["vendor"] else "",
                "date missing" if not row["date"] else "",
                "total missing" if row["total"] is None else "") if x]
            row["status"] = "review" if row["problems"] else "ok"
            save_receipts(rows)
            return self.send_json(row)

    def do_DELETE(self):
        if not self.same_origin():
            return self.send_json({"error": "Blocked"}, 403)
        rid = os.path.basename(urllib.parse.urlparse(self.path).path)
        with LOCK:
            rows = load_receipts()
            row = next((r for r in rows if r["id"] == rid), None)
            if not row:
                return self.send_json({"error": "Not found"}, 404)
            save_receipts([r for r in rows if r["id"] != rid])
            try:
                os.remove(os.path.join(IMAGES, rid + "." + row["image_ext"]))
            except OSError:
                pass
        return self.send_json({"ok": True})

    # -- actions
    def status(self):
        s = load_settings()
        out = {"demo": s["demo"], "model": s["model"], "ollama": False, "model_installed": False, "models": []}
        try:
            tags = ollama_json(s, "/api/tags", timeout=2)
            names = [m.get("name", "") for m in tags.get("models", [])]
            out["ollama"] = True
            out["models"] = names
            want = s["model"]
            out["model_installed"] = any(n == want or n.split(":")[0] == want or (":" not in want and n.startswith(want + ":")) for n in names)
        except Exception:
            pass
        return out

    def scan(self, filename):
        settings = load_settings()
        try:
            raw = self.body()
        except ValueError as e:
            return self.send_json({"error": str(e)}, 413)
        ext = sniff_image(raw)
        if ext is None:
            return self.send_json({"error": "This file is not a picture. Use a JPG, PNG or WEBP photo of the bill."}, 415)
        if ext == "pdf":
            return self.send_json({"error": "PDFs are not supported yet. Take a photo or screenshot of the bill instead."}, 415)
        t0 = time.time()
        try:
            if settings["demo"]:
                parsed, meta = read_demo(filename)
                img, ext2 = raw, ext
            else:
                img, ext2 = prepare_image(raw, ext)
                parsed, meta = read_with_gemma(settings, img)
        except ModelError as e:
            return self.send_json({"error": str(e)}, 502)
        rec = normalise(parsed, settings, filename)
        rid = uuid.uuid4().hex[:12]
        rec.update({
            "id": rid, "filename": filename[:120], "added": datetime.now().isoformat(timespec="seconds"),
            "image_ext": ext2, "demo": bool(settings["demo"]), "edited": False,
            "seconds": round(time.time() - t0, 1), "model": "demo" if settings["demo"] else settings["model"],
            "tokens": meta.get("tokens"),
        })
        with LOCK:
            rows = load_receipts()
            twin = next((r for r in rows if r["vendor"].lower() == rec["vendor"].lower() and rec["vendor"]
                         and r["date"] == rec["date"] and r["total"] == rec["total"]), None)
            if twin:
                rec["duplicate_of"] = twin["id"]
                rec["problems"].append("looks like a duplicate of an earlier bill")
                rec["status"] = "review"
            with open(os.path.join(IMAGES, rid + "." + ext2), "wb") as f:
                f.write(img)
            rows.append(rec)
            save_receipts(rows)
        return self.send_json(rec)

    def export_csv(self, month):
        names = {c["id"]: c["name"] for c in CATEGORIES}
        with LOCK:
            rows = load_receipts()
        rows = [r for r in rows if not month or (r["date"] or "").startswith(month)]
        rows.sort(key=lambda r: (r["date"] or "9999", r["vendor"]))
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["Date", "Vendor", "Category", "Total", "Tax", "Currency", "Paid by", "Items", "Notes", "Needs a check", "File"])
        for r in rows:
            w.writerow([
                r["date"], r["vendor"], names.get(r["category"], r["category"]),
                "" if r["total"] is None else "%.2f" % r["total"],
                "" if r["tax"] is None else "%.2f" % r["tax"],
                r["currency"], r["payment"],
                "; ".join(i["name"] for i in r["items"]), r["notes"],
                "yes" if r["status"] == "review" else "", r["filename"],
            ])
        body = ("﻿" + buf.getvalue()).encode("utf-8")  # BOM so Excel shows the rupee sign correctly
        fname = "tallyroll-%s.csv" % (month or "all")
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", 'attachment; filename="%s"' % fname)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    port = int(os.environ.get("PORT", "8765"))
    srv = None
    for p in range(port, port + 11):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", p), Handler)
            port = p
            break
        except OSError:
            continue
    if srv is None:
        print("Could not find a free port. Close other programs and try again.")
        sys.exit(1)
    url = "http://127.0.0.1:%d" % port
    print("")
    print("  Tallyroll is running.")
    print("  Open this address in your browser:  %s" % url)
    print("  (Keep this window open while you use Tallyroll. Close it to stop.)")
    print("")
    if "--no-browser" not in sys.argv:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
