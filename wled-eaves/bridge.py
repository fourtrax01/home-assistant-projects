#!/usr/bin/env python3
"""WLED -> Govee H7076 bridge.

WLED sends the porch lights' pixels as a virtual "DDP RGB" output (6 lights x 36 beads = 216 LEDs).
This bridge receives that DDP stream and forwards each light's 36 beads to it with Govee's LAN
"razer" (DreamView) streaming command, so WLED effects run across the eaves AND the porch lights.

Bead order per light (same as the DIY map): 0 top, 1 bottom, 2-18 one side strip, 19-35 the other.
PIXELS = WLED pixels per light. 36 = raw beads. Fewer (e.g. 10, for a WLED ledmap that inserts each
light into the eave strip at its real position) = [top, rows top->bottom..., bottom]: each row lights
the matching height on BOTH side strips, so a chase entering from the eave flows down through the light.
Forwarding only happens while enabled (HTTP control, so HA's normal porch looks still work):
  GET /on   GET /off   GET /status
No dependencies beyond the Python standard library.

Env:
  GOVEE_IPS   comma-separated light IPs in strip order (required)
  PIXELS      WLED pixels per light (default 10; 36 = raw beads)
  DDP_PORT    default 4048 (WLED's DDP port)
  HTTP_PORT   default 8790
  BIND_HOST   address the HTTP control listens on (default 0.0.0.0 = all interfaces). Set it to
              the host's LAN address. Never forward this port to the internet.
  ALLOW_FROM  comma-separated IPs/CIDRs allowed to use the HTTP control and to send DDP
              (default: private LAN + loopback ranges only). Best: your HA IP and WLED IP.
  BRIDGE_TOKEN optional shared secret. If set, every HTTP request must send it as the
              X-Bridge-Token header or ?token=... (stops other LAN devices and web pages).
  MAX_FPS     per-light frame cap (default 25)
  ENABLED     1 to start enabled (default 0)
  FLOOR_PCT   porch never goes below this % of FLOOR_RGB while streaming (default 30; 0 = off)
  FLOOR_RGB   floor color, hex (default ffbe4b = the porch warm white)
Live tuning (no redeploy): GET /floor?pct=20&rgb=ffbe4b keeps the porch lights at ~20% warm white
instead of going dark between effects.
"""
import base64, hmac, ipaddress, json, math, os, socket, threading, time
from urllib.parse import urlparse, parse_qs
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

IPS = [ip.strip() for ip in os.environ["GOVEE_IPS"].split(",") if ip.strip()]
BEADS = 36
PIXELS = int(os.environ.get("PIXELS", 10))
SIDE = 17
DDP_PORT = int(os.environ.get("DDP_PORT", 4048))
HTTP_PORT = int(os.environ.get("HTTP_PORT", 8790))
MIN_GAP = 1.0 / float(os.environ.get("MAX_FPS", 25))
GOVEE_PORT = 4003
REENABLE_EVERY = 5.0  # re-send razer enable so a light that rebooted rejoins the stream
BIND_HOST = os.environ.get("BIND_HOST", "0.0.0.0")
ALLOW_FROM = [ipaddress.ip_network(n.strip(), strict=False) for n in os.environ.get(
    "ALLOW_FROM", "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,127.0.0.0/8").split(",") if n.strip()]
TOKEN = os.environ.get("BRIDGE_TOKEN", "")


def allowed(ip):
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(a in n for n in ALLOW_FROM)

state = {"enabled": os.environ.get("ENABLED", "0") == "1", "frames_in": 0, "frames_out": 0,
         "last_in": 0.0, "started": time.time(),
         "floor_pct": float(os.environ.get("FLOOR_PCT", 30)), "floor_rgb": os.environ.get("FLOOR_RGB", "ffbe4b")}


def floor_bytes():
    rgb = bytes.fromhex(state["floor_rgb"])
    return bytes(int(c * state["floor_pct"] / 100) for c in rgb)


def apply_floor(rgb, fl):
    """Dark beads glow at the floor color; the floor fades out as the bead gets brighter, so full
    effect colors stay pure (a plain channel max tinted pure red orange)."""
    if not any(fl):
        return rgb
    out = bytearray(rgb)
    for i in range(0, len(out), 3):
        k = 1.0 - max(out[i], out[i + 1], out[i + 2]) / 255.0
        if k > 0:
            for c in range(3):
                out[i + c] = min(255, out[i + c] + int(fl[c] * k))
    return bytes(out)
buf = bytearray(len(IPS) * PIXELS * 3)


def expand(px):
    """PIXELS rgb triples -> 36 bead rgb bytes (bead 0 top, 1 bottom, 2-18 / 19-35 sides bottom->top)."""
    if PIXELS == BEADS:
        return px
    cols = [px[i * 3:i * 3 + 3] for i in range(PIXELS)]
    rows = cols[1:-1] or [cols[0]]          # side rows, top -> bottom
    side = []
    for b in range(SIDE):                   # b = 0 bottom .. 16 top
        r = int((SIDE - 1 - b) * len(rows) / SIDE)
        side.append(rows[min(r, len(rows) - 1)])
    return b"".join([cols[0], cols[-1]] + side + side)
lock = threading.Lock()
new_frame = threading.Event()   # set on each DDP PUSH so frames go out at once (11-22: porch lagged the eaves)
out = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


def log(*a):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), *a, flush=True)


def razer(ip, payload):
    cs = 0
    for b in payload:
        cs ^= b
    msg = {"msg": {"cmd": "razer", "data": {"pt": base64.b64encode(bytes(payload) + bytes([cs])).decode()}}}
    out.sendto(json.dumps(msg).encode(), (ip, GOVEE_PORT))


def set_stream(on):
    for ip in IPS:
        razer(ip, [0xBB, 0x00, 0x01, 0xB1, 0x01 if on else 0x00])


def send_light(i, rgb):
    razer(IPS[i], [0xBB, 0x00, len(rgb) + 2, 0xB0, 0x00, BEADS] + list(rgb))


def ddp_listener():
    """DDP header (10 bytes): flags, seq, type, id, offset(4, big-endian), length(2). Data = RGB bytes."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind((BIND_HOST, DDP_PORT))
    log("DDP listening on", BIND_HOST, DDP_PORT, "lights:", IPS)
    while True:
        pkt, src = s.recvfrom(2048)
        if len(pkt) < 10 or not allowed(src[0]):
            continue
        flags = pkt[0]
        hdr = 14 if flags & 0x10 else 10  # timecode flag adds 4 bytes
        off = int.from_bytes(pkt[4:8], "big")
        data = pkt[hdr:hdr + int.from_bytes(pkt[8:10], "big")]
        with lock:
            end = min(len(buf), off + len(data))
            if off < len(buf):
                buf[off:end] = data[:end - off]
            if flags & 0x01:  # PUSH = frame complete
                state["frames_in"] += 1
                state["last_in"] = time.time()
                new_frame.set()


def sender():
    last_frame, last_enable, was_on = -1, 0.0, False
    while True:
        on = state["enabled"]
        if on and not was_on:
            log("stream ON")
            last_enable = 0.0
        if was_on and not on:
            log("stream OFF")
            set_stream(False)
        was_on = on
        if not on:
            time.sleep(0.2)
            continue
        now = time.time()
        if now - last_enable > REENABLE_EVERY:
            set_stream(True)
            last_enable = now
        new_frame.wait(0.2); new_frame.clear()
        if state["frames_in"] != last_frame:
            sent_at = time.time()
            last_frame = state["frames_in"]
            with lock:
                snap = bytes(buf)
            fl = floor_bytes()
            for i in range(len(IPS)):
                send_light(i, apply_floor(expand(snap[i * PIXELS * 3:(i + 1) * PIXELS * 3]), fl))
            state["frames_out"] += 1
            gap = MIN_GAP - (time.time() - sent_at)   # still cap at MAX_FPS
            if gap > 0: time.sleep(gap)


class Http(BaseHTTPRequestHandler):
    def _deny(self, code):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"error": "forbidden"}')

    def do_GET(self):
        u = urlparse(self.path); path = u.path
        q = parse_qs(u.query)
        if not allowed(self.client_address[0]):
            return self._deny(403)
        if TOKEN:
            sent = self.headers.get("X-Bridge-Token") or (q.get("token") or [""])[0]
            if not hmac.compare_digest(sent.encode(), TOKEN.encode()):
                return self._deny(401)
        if path in ("/on", "/off"):
            state["enabled"] = path == "/on"
        if path == "/floor":
            # Validate before storing: a short rgb (e.g. "ff") used to crash the sender thread.
            try:
                if "pct" in q:
                    pct = float(q["pct"][0])
                    if math.isfinite(pct):
                        state["floor_pct"] = max(0.0, min(100.0, pct))
                if "rgb" in q:
                    rgb = q["rgb"][0].strip().lstrip("#")
                    if len(rgb) == 6:
                        bytes.fromhex(rgb)
                        state["floor_rgb"] = rgb.lower()
            except ValueError:
                pass
            log("floor", state["floor_pct"], state["floor_rgb"])
        body = json.dumps({"enabled": state["enabled"], "frames_in": state["frames_in"],
                           "frames_out": state["frames_out"],
                           "receiving": time.time() - state["last_in"] < 2,
                           "lights": IPS, "uptime_s": int(time.time() - state["started"]),
                           "floor_pct": state["floor_pct"], "floor_rgb": state["floor_rgb"]}).encode()
        self.send_response(200 if path in ("/on", "/off", "/status", "/floor", "/") else 404)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    threading.Thread(target=ddp_listener, daemon=True).start()
    threading.Thread(target=sender, daemon=True).start()
    log("HTTP control on", BIND_HOST, HTTP_PORT, "(/on /off /status /floor), enabled =", state["enabled"],
        "floor", state["floor_pct"], state["floor_rgb"], "token", "on" if TOKEN else "off",
        "allow", ",".join(str(n) for n in ALLOW_FROM))
    ThreadingHTTPServer((BIND_HOST, HTTP_PORT), Http).serve_forever()
