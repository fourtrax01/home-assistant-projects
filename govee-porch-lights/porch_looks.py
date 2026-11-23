#!/usr/bin/env python3
"""Porch H7076 looks over LAN (per-bead DIY, see porch.py). Built 2026-11-13.
Usage: porch_looks.py list | stop | <look> [seconds] [bri=1-100]
Lights left->right from the street: porch, walk_porch, walkway, left, center, right.
Each light = top, bottom, 17 left dots (bottom->top), 17 right dots (bottom->top).
"""
import os, sys, time, colorsys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import porch

RUNFILE = "/config/govee_tools/.porch.run"
ORDER = ["porch", "walk_porch", "walkway", "left", "center", "right"]
N = 17
FX = {"up": 0x09, "down": 0x0a, "cw": 0x02, "ccw": 0x03, "twinkle": 0x0f, "breathe": 0x14}

RED, GREEN, WHITE, BLUE = "ff0000", "00ff00", "ffffff", "0028ff"
WARM = "ffbe4b"            # user-approved side warm (255,190,75)
ORANGE, PURPLE = "ff6400", "b400ff"
PINK, CYAN, GOLD = "ff1478", "00ffff", "ffb400"
SOFT = "ffd890"         # between WARM and WHITE for top/bottom (tuning 11-13)


def hx(rgb): return "%02x%02x%02x" % tuple(max(0, min(255, int(c))) for c in rgb)
def hsv(h, s=1, v=1): return hx([c * 255 for c in colorsys.hsv_to_rgb(h % 1, s, v)])
def lerp(a, b, t):
    a, b = bytes.fromhex(a), bytes.fromhex(b)
    return hx([x + (y - x) * t for x, y in zip(a, b)])
def grad(a, b): return [lerp(a, b, i / (N - 1)) for i in range(N)]
def stripes(colors, width, offset=0): return [colors[((i + offset) // width) % len(colors)] for i in range(N)]


def light(top, bottom, left, right=None, effect=None, speed=0):
    """left/right = one color or a list of 17 (bottom->top). right defaults to a mirror of left."""
    if right is None: right = left
    if isinstance(left, str): left = [left] * N
    if isinstance(right, str): right = [right] * N
    return dict(top=top, bottom=bottom, left=left, right=right, effect=effect, speed=speed)


def frames(spec):
    groups = {}
    groups.setdefault(spec["top"], []).append(0)
    groups.setdefault(spec["bottom"], []).append(1)
    for i, c in enumerate(spec["left"]): groups.setdefault(c, []).append(porch.LEFT[i])
    for i, c in enumerate(spec["right"]): groups.setdefault(c, []).append(porch.RIGHT[i])
    if spec["effect"] is None:
        return porch.diy(list(groups.items()))
    return porch.diy(list(groups.items()), effect=FX[spec["effect"]], speed=spec["speed"], flag=0x01)


def show(specs, bri=None, repeat=3):
    """UDP can drop a packet (Center missed one 11-13), so static sends go out twice."""
    for r in range(repeat):
        for name, spec in zip(ORDER, specs):
            if spec is None: continue          # None = leave this light as it is
            ip = porch.IPS[name]
            porch.send(ip, [porch.frame(b"\x33\x01\x01")] + frames(spec))
            if bri: porch.brightness(ip, bri)
        if r < repeat - 1: time.sleep(0.3)


# ---------------- static looks (one spec per light) ----------------
def s_warm():        # normal evening look, all local
    return [light(WARM, WARM, WARM)] * 6

def s_candy_cane():
    return [light(RED if i % 2 else WHITE, WHITE if i % 2 else RED, stripes([RED, WHITE], 3, i), stripes([RED, WHITE], 3, i + 3))
            for i in range(6)]

def s_christmas():   # house reads G R G R G R (user rule), striped sides
    out = []
    for i in range(6):
        a, b = (GREEN, RED) if i % 2 == 0 else (RED, GREEN)
        out.append(light(a, SOFT, stripes([b, a], 2), stripes([a, b], 2)))
    return out

def s_christmas_gold():
    return [light(RED if i % 2 else GREEN, GOLD, grad(GOLD, RED if i % 2 else GREEN)) for i in range(6)]

def s_usa():         # red top, blue bottom, sides white->red stripes with a blue band at the top
    side = stripes([RED, WHITE], 2)[:12] + [BLUE] * 5
    return [light(RED, BLUE, side)] * 6

def s_halloween():
    out = []
    for i in range(6):
        a, b = (ORANGE, PURPLE) if i % 2 == 0 else (PURPLE, ORANGE)
        out.append(light(a, "00ff1e", grad(b, a)))
    return out

def s_rainbow():     # each light its own hue, sides a full rainbow
    return [light(hsv(i / 6), hsv(i / 6 + .5), [hsv(j / N) for j in range(N)]) for i in range(6)]

def s_rainbow_row(): # one rainbow spread across all six lights
    return [light(hsv(i / 6), hsv(i / 6), [hsv(i / 6 + j / (N * 6)) for j in range(N)]) for i in range(6)]

def s_valentine():
    return [light(RED, PINK, grad(RED, PINK)) for _ in range(6)]

def s_ice():
    return [light(WHITE, "0050ff", grad("0030ff", "a0e0ff")) for _ in range(6)]

def s_fall():
    return [light(ORANGE, "ff3000", grad("ff2000", GOLD)) for _ in range(6)]

def s_multicolor():  # the approved Christmas multicolor tops, sides from 3 lights away
    tops = [CYAN, PURPLE, GREEN, PINK, ORANGE, "0040ff"]
    return [light(tops[i], WARM, tops[(i + 3) % 6]) for i in range(6)]


# ------------- on-light effects (light animates itself, no streaming) -------------
def e_candy_climb():
    return [dict(s, effect="up", speed=10) for s in s_candy_cane()]

def e_christmas_spin():
    return [dict(s, effect="cw" if i % 2 else "ccw", speed=15) for i, s in enumerate(s_christmas())]

def e_rainbow_spin():
    return [light(hsv(i / 6), hsv(i / 6 + .5), [hsv(j / (2 * N)) for j in range(N)],
                  [hsv(1 - j / (2 * N)) for j in range(N)], effect="cw", speed=20) for i in range(6)]

def e_christmas_twinkle():
    return [dict(s, effect="twinkle", speed=20) for s in s_christmas()]


BRI = 100   # target brightness for brightness-driven animations (set from bri= in main)


def a_halloween_breathe():
    """Halloween colors held still; brightness breathes over LAN (the light's own DIY
    Breathe effect just went dim and stayed there, user 11-13 and 11-22). An int frame
    = brightness only for all six. ~5 s cycle, 15% -> target, 0.05 s steps (0.25 s looked stepped, 0.1 s "better", user 11-22)."""
    import math
    yield s_halloween(), 0.5
    lo, t, step, last = 15, 0.0, 0.05, None
    while True:
        hi = max(lo + 5, BRI)
        v = int(round(lo + (hi - lo) * (0.5 - 0.5 * math.cos(2 * math.pi * t / 5.0))))
        t += step
        if v == last:                 # skip repeats (cuts traffic near the ends)
            time.sleep(step); continue
        last = v
        yield v, step


# ---------------- streamed animations (yield specs, delay) ----------------
def a_color_chase():   # whole-light colors move down the row
    pal = [RED, ORANGE, "ffff00", GREEN, "00a0ff", PURPLE]
    k = 0
    while True:
        yield [light(pal[(i - k) % 6], pal[(i - k) % 6], grad(pal[(i - k) % 6], pal[(i - k + 1) % 6]))
               for i in range(6)], 1.0
        k += 1

def a_christmas_chase():   # red/green swap down the row
    k = 0
    while True:
        yield [light(RED if (i + k) % 2 else GREEN, WARM, RED if (i + k) % 2 else GREEN) for i in range(6)], 1.5
        k += 1

def a_rainbow_flow():      # rainbow scrolls across the whole row
    k = 0
    while True:
        yield [light(hsv(i / 6 + k), hsv(i / 6 + k), [hsv(i / 6 + j / (N * 6) + k) for j in range(N)])
               for i in range(6)], 0.5
        k += 0.02

def a_wave():              # a white wave rolls down the row over a blue base
    k = 0
    while True:
        out = []
        for i in range(6):
            t = max(0, 1 - abs(((k - i) % 8) - 1))
            c = lerp("0030ff", WHITE, t)
            out.append(light(c, "0030ff", grad("0030ff", c)))
        yield out, 0.4
        k += 0.5


def a_usa_climb():        # blue band + red top/blue bottom fixed; red/white stripes roll upward
    k = 0
    while True:
        side = [[RED, RED, WHITE, WHITE][(j - k) % 4] for j in range(12)] + [BLUE] * 5
        yield [light(RED, BLUE, side)] * 6, 0.7
        k += 1


def a_lightning():          # stormy purple; strikes = light's own Up effect at top speed (white top/dark bottom
    import random           # swap = bottom/top flicker run on the light itself, no network lag). Tuned 11-13.
    base = [light("3c0078", "5000a0", grad("28005a", "7800ff")) for _ in range(6)]   # 2x brighter 11-13 (user)
    strike = light(WHITE, "010000", "7800ff", effect="up", speed=0x64)
    yield base, 1.0
    while True:
        r = random.random()
        if r < 0.2: hit = list(range(6))                       # whole porch
        else:
            n = random.choice([1, 1, 2, 3]); s = random.randint(0, 6 - n); hit = list(range(s, s + n))
        random.shuffle(hit)                                    # lights in a strike go off slightly out of step
        for _ in range(random.choice([1, 1, 1, 2, 3])):        # flickers in this strike
            for j, i in enumerate(hit):
                yield [strike if k == i else None for k in range(6)], random.uniform(0, 0.08)
            yield [None] * 6, random.uniform(0.2, 0.5)
            yield [base[i] if i in hit else None for i in range(6)], random.uniform(0.1, 0.4)
        # gaps: mostly a lull, sometimes a quick follow-up, sometimes a long calm
        g = random.random()
        yield [None] * 6, (random.uniform(0.3, 1.2) if g < 0.25 else
                           random.uniform(1.5, 6) if g < 0.8 else random.uniform(8, 18))


STATIC = {k[2:]: v for k, v in globals().items() if k.startswith(("s_", "e_"))}
ANIM = {k[2:]: v for k, v in globals().items() if k.startswith("a_")}


# head start (s) for lights on slower Wi-Fi so Govee scenes start in step
# (11-22: Right + Center ~110 ms ping, behind on ZDP Duo; tuned by eye)
GOVEE_LEAD = {"right": 0.10, "center": 0.07}
GOVEE_LAST = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".porch_govee_scene")


# ---------------- eaves (WLED .201) matching a Govee scene ----------------
WLED = "http://192.168.1.70/json/state"
# WLED playlist 49 "Eaves Scene Rotate" = effect-only presets 40-45 (Colortwinkles, Twinklefox,
# Colorwaves, Flow, Palette, Juggle), 2 min each, 3 s crossfade, loops (user 11-22: "rotate")
EAVES_ROTATE, EAVES_FX = 49, (74, 80, 67, 110, 65, 64)
EAVES_SAVED = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".eaves_saved.json")


def _wled(body=None):
    import json, urllib.request
    req = urllib.request.Request(WLED, data=json.dumps(body).encode() if body else None,
                                 headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=4))


def eaves_match(colors, bri_pct):
    """Eaves in the scene's colors, rotating WLED effects (playlist EAVES_ROTATE, starts on Colortwinkles).
    The eaves' state before the first Govee scene is saved once, for eaves_restore."""
    import json
    try:
        if not os.path.exists(EAVES_SAVED):
            st = _wled(); seg = st["seg"][0]
            json.dump({"on": st["on"], "bri": st["bri"], "ps": st.get("ps", -1), "pl": st.get("pl", -1),
                       "seg": {k: seg.get(k) for k in ("fx", "pal", "col", "sx", "ix")}}, open(EAVES_SAVED, "w"))
        cols = [list(bytes.fromhex(c)) for c in colors[:3]]
        pal = {0: 11, 1: 2, 2: 3}.get(len(cols), 5)    # none -> Rainbow, 1 -> Color 1, 2 -> Colors 1&2, 3 -> Colors only
        while len(cols) < 3: cols.append([0, 0, 0])
        body = {"on": True, "bri": max(1, round(bri_pct * 2.55)), "transition": 15,
                "seg": [{"id": 0, "fx": 74, "pal": pal, "sx": 96, "ix": 128, "col": cols}]}
        _wled(body)
        _wled({"ps": EAVES_ROTATE})          # rotate effects (colors/palette stay)
        st = json.load(open(EAVES_SAVED)); st["ours"] = {"fx": 74, "pal": pal, "col": cols}
        json.dump(st, open(EAVES_SAVED, "w"))
    except Exception as e:
        print("eaves:", e, file=sys.stderr)


def eaves_restore():
    """Put the eaves back to their pre-Govee-scene state, but only if they still show our
    twinkle (if midnight/sunrise/arrival automations changed them since, leave them)."""
    import json
    try: saved = json.load(open(EAVES_SAVED))
    except OSError: return
    try:
        st = _wled(); seg = st["seg"][0]; ours = saved.get("ours", {})
        if st["on"] and (seg.get("fx") in EAVES_FX or st.get("pl") == EAVES_ROTATE) and seg.get("pal") == ours.get("pal") \
                and [c[:3] for c in seg.get("col", [])[:3]] == [c[:3] for c in ours.get("col", [])]:
            if saved.get("pl", -1) > 0: _wled({"ps": saved["pl"]})
            elif saved.get("ps", -1) > 0: _wled({"ps": saved["ps"]})
            else: _wled({"on": saved["on"], "bri": saved["bri"], "transition": 15,
                         "seg": [dict({"id": 0}, **saved["seg"])]})
    except Exception as e:
        print("eaves restore:", e, file=sys.stderr)
    finally:
        try: os.remove(EAVES_SAVED)
        except OSError: pass


def stop_running():
    open(RUNFILE, "w").write("stop")
    me = os.getpid()
    for d in os.listdir("/proc"):
        if not d.isdigit() or int(d) == me: continue
        try: cmd = open(f"/proc/{d}/cmdline", "rb").read().split(b"\0")
        except OSError: continue
        if any(a.endswith(b"porch_looks.py") for a in cmd) and b"python3" in cmd[0]:
            try: os.kill(int(d), 15)
            except OSError: pass


def run_anim(gen, seconds, bri):
    token = "%d-%f" % (os.getpid(), time.time())
    open(RUNFILE, "w").write(token)
    if os.fork(): return
    os.setsid()
    if os.fork(): os._exit(0)
    fd = os.open(os.devnull, os.O_RDWR)
    for f in (0, 1, 2): os.dup2(fd, f)
    end = time.time() + seconds if seconds else None
    first = True
    try:
        for specs, delay in gen():
            try:
                if open(RUNFILE).read() != token: break
            except OSError: break
            if isinstance(specs, int):         # brightness-only frame
                for ip in porch.IPS.values(): porch.brightness(ip, specs)
            else:
                show(specs, bri if first else None, repeat=1)
            first = False
            time.sleep(delay)
            if end and time.time() > end: break
    finally:
        os._exit(0)


def main():
    args = sys.argv[1:]
    bri = None
    for a in list(args):
        if a.startswith("bri="): bri = int(a[4:]); args.remove(a)
    name = args[0] if args else "list"
    global BRI
    if bri: BRI = bri
    secs = float(args[1]) if len(args) > 1 else 0
    if name == "list":
        print("static/effect:", " ".join(STATIC)); print("animated:", " ".join(ANIM)); return
    if name == "eaves_restore":             # doesn't stop a look that may be starting
        eaves_restore(); return
    stop_running()
    if name == "stop": return
    if name == "off":                      # stop + power all six off over LAN (sent twice)
        for _ in range(2):
            for ip in porch.IPS.values(): porch.send(ip, [porch.frame(b"\x33\x01\x00")])
            time.sleep(0.3)
        return
    if name == "govee_scene":               # porch_look "Govee Scene" = replay the last govee:<name>
        try: name = "govee:" + open(GOVEE_LAST).read().strip()
        except OSError: sys.exit(2)
    eaves = True
    if name.endswith("__day"):              # picked by day: porch only, eaves untouched
        name, eaves = name[:-5], False
    if name.startswith("govee:"):
        # Govee built-in scene (h7076_effects.json via govee_scene.py) on all six at once.
        # One process sends to every light back to back so they start together; the second
        # pass covers a dropped UDP packet (it restarts the scene, all six together). Exit 2 if unknown.
        import govee_scene
        fr = govee_scene.frames_for(name[6:], "H7076")
        if fr is None: sys.exit(2)
        try: open(GOVEE_LAST, "w").write(name[6:] + ("" if eaves else "__day"))
        except OSError: pass
        order = sorted(porch.IPS, key=lambda n: -GOVEE_LEAD.get(n, 0))
        for r in range(2):
            for i, n in enumerate(order):     # slow-Wi-Fi lights get a head start
                govee_scene.send_frames(porch.IPS[n], fr)
                nxt = GOVEE_LEAD.get(order[i + 1], 0) if i + 1 < len(order) else None
                if nxt is not None and GOVEE_LEAD.get(n, 0) > nxt: time.sleep(GOVEE_LEAD.get(n, 0) - nxt)
            if r == 0: time.sleep(0.3)
        if bri:
            for ip in porch.IPS.values(): porch.brightness(ip, bri)
        if eaves: eaves_match(govee_scene.scene_palette(name[6:]), bri or 100)
        return
    if name in STATIC: show(STATIC[name](), bri)
    elif name in ANIM: run_anim(ANIM[name], secs, bri)
    else: sys.exit(f"unknown look {name}")


if __name__ == "__main__":
    main()
