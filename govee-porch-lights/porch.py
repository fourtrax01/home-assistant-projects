#!/usr/bin/env python3
"""Govee H7076 per-bead control over LAN (UDP 4003 ptReal), decoded from BLE capture 2026-11-13.
IDs: 0 = top, 1 = bottom, 2..18 = left strip (2 bottom .. 18 top), 19..35 = right strip (19 bottom .. 35 top).
Usage: porch.py IP top=RRGGBB bottom=RRGGBB left=RRGGBB right=RRGGBB 5=RRGGBB ... [bri=1-100]
       porch.py IP off|on
"""
import socket, json, base64, sys
LEFT = list(range(2, 19)); RIGHT = list(range(19, 36))
NAMES = {"top": [0], "bottom": [1], "left": LEFT, "right": RIGHT}

def frame(b):
    b = bytes(b) + bytes(19 - len(b)); cs = 0
    for x in b: cs ^= x
    return b + bytes([cs])

def diy(groups, bri=100, effect=0x09, speed=0x00, mode=0x03, flag=0x02, tail=b"\xff\xff\xff"):
    """groups: list of (rgb_hex, [ids]). flag 0x02 = STILL (tested 11-13); flag 0x01 = animate with effect (09 Up,0a Down,02 CW,03 CCW,0f Twinkle,14 Breathe; 00 = side chase), speed 0 slow..0x64 fast; flag 0 = top/bottom still, sides animate."""
    # top/bottom (ids 0,1) show cool white for 000000 or when omitted; 010000 = off (tested 11-13)
    fixed = []
    for rgb, ids in groups:
        tb = [i for i in ids if i in (0, 1)]
        if rgb.lower() == "000000" and tb:
            fixed.append(("010000", tb)); ids = [i for i in ids if i not in (0, 1)]
        if ids: fixed.append((rgb, ids))
    groups = fixed
    data = bytes([mode, effect, speed, flag, bri]) + tail + bytes([len(groups)])
    for rgb, ids in groups:
        data += bytes([len(ids)]) + bytes.fromhex(rgb) + bytes(ids)
    chunks = [data[:15]] + [data[i:i+17] for i in range(15, len(data), 17)]
    n = len(chunks)
    out = [frame(b"\xa3\x00\x01" + bytes([n]) + chunks[0])]
    for i, c in enumerate(chunks[1:], 1):
        out.append(frame(bytes([0xa3, 0xff if i == n - 1 else i]) + c))
    if n == 1:
        out.append(frame(b"\xa3\xff"))
    out.append(frame(b"\x33\x05\x0a\x20\x03"))
    return out

IPS = {"porch": "192.168.1.51", "walk_porch": "192.168.1.52", "walkway": "192.168.1.53",
       "left": "192.168.1.54", "center": "192.168.1.55", "right": "192.168.1.56"}  # left-to-right from street

def lan(ip, cmd, data):
    socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(json.dumps({"msg": {"cmd": cmd, "data": data}}).encode(), (ip, 4003))

def brightness(ip, pct):
    """DIY header brightness is ignored; the LAN brightness cmd keeps the pattern (tested 11-13)."""
    lan(ip, "brightness", {"value": int(pct)})

def send(ip, frames):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    msg = {"msg": {"cmd": "ptReal", "data": {"command": [base64.b64encode(f).decode() for f in frames]}}}
    s.sendto(json.dumps(msg).encode(), (ip, 4003))

if __name__ == "__main__":
    ip, args = sys.argv[1], sys.argv[2:]
    if args == ["off"]: send(ip, [frame(b"\x33\x01\x00")]); sys.exit()
    if args == ["on"]: send(ip, [frame(b"\x33\x01\x01")]); sys.exit()
    bri = 100; colors = {}
    for a in args:
        k, v = a.split("=")
        if k == "bri": bri = int(v); continue
        ids = NAMES.get(k) or [int(x) for x in k.split(",")]
        colors.setdefault(v.lower(), []).extend(ids)
    send(ip, [frame(b"\x33\x01\x01")] + diy(list(colors.items())))
    if bri != 100: import time; time.sleep(0.5); brightness(ip, bri)
