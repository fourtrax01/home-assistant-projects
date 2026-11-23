#!/usr/bin/env python3
"""Govee H6069 heart (20 mini panels) - local per-panel scenes and animations.

usage: heart.py <scene> [seconds]      list scenes: heart.py list
Static scenes send once. Animations run in the background (detached) until
another scene is sent, `heart.py stop`, or the optional duration ends.
Protocol: LAN UDP 4003 ptReal, multi-packet a3 "DIY" message, entry
01 RR GG BB <panel>, then commit 33 05 0a 20 03 (decoded 2026-11-13).
"""
import base64, colorsys, json, math, os, random, signal, socket, sys, time

IP = "192.168.1.60"
RUNFILE = "/config/govee_tools/.heart.run"   # token of the animation allowed to run

# panel -> (row, col) as seen on the wall; row 0 = top, col grows to the right
POS = {15: (0, 0), 6: (0, 4), 14: (1, -1), 17: (1, 1), 7: (1, 3), 5: (1, 5),
       13: (2, -2), 16: (2, 0), 4: (2, 4), 19: (2, 6), 12: (3, -1), 10: (3, 1),
       3: (3, 3), 18: (3, 5), 11: (4, 0), 8: (4, 2), 2: (4, 4), 1: (5, 3),
       9: (5, 1), 0: (6, 2)}
PANELS = sorted(POS)
CX, CY = 2.0, 2.6                      # visual centre of the heart
# outline, clockwise from the bottom tip
OUTLINE = [0, 9, 11, 12, 13, 14, 15, 17, 7, 6, 5, 19, 18, 2, 1]
ORIGINAL = {0: "ff0000", 1: "ffb205", 2: "caff02", 3: "13c4ff", 4: "12fffd",
            5: "0affa5", 6: "ff15e7", 7: "f517ff", 8: "1149ff", 9: "1e1eff",
            10: "af1dff", 11: "5423ff", 12: "fff679", 13: "90ff78", 14: "98fffb",
            15: "fe65ff", 16: "ff6b6b", 17: "ff1a48", 18: "40ff01", 19: "00ff05"}

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


def _frame(b):
    b = bytes(b) + bytes(19 - len(b))
    cs = 0
    for x in b:
        cs ^= x
    return b + bytes([cs])


def send_raw(frames):
    msg = {"msg": {"cmd": "ptReal", "data": {"command":
           [base64.b64encode(f).decode() for f in frames]}}}
    sock.sendto(json.dumps(msg).encode(), (IP, 4003))


def show(colors):
    """colors: {panel: (r,g,b) 0-255 or 'rrggbb'}"""
    data = bytearray()
    for p in PANELS:
        c = colors.get(p, (0, 0, 0))
        if isinstance(c, str):
            c = bytes.fromhex(c)
        data += bytes([1]) + bytes(max(0, min(255, int(v))) for v in c) + bytes([p])
    first, rest = data[:7], data[7:]
    chunks = []
    while rest:
        chunks.append(rest[:17])
        rest = rest[17:]
    frames = [_frame(b"\xa3\x00" + bytes([1, 1 + max(1, len(chunks)), 3, 0, 0, 0, 0, 0, 0,
                                          len(PANELS)]) + first)]
    for n, c in enumerate(chunks):
        frames.append(_frame(bytes([0xa3, 0xff if n == len(chunks) - 1 else n + 1]) + c))
    frames.append(_frame(bytes.fromhex("33050a2003")))
    send_raw(frames)


def power_on():
    send_raw([_frame(bytes.fromhex("330101"))])


def hsv(h, s=1.0, v=1.0):
    return tuple(int(x * 255) for x in colorsys.hsv_to_rgb(h % 1.0, s, v))


def mix(a, b, t):
    a, b = (bytes.fromhex(x) if isinstance(x, str) else x for x in (a, b))
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def grad(stops, t):
    t = max(0.0, min(1.0, t)) * (len(stops) - 1)
    i = min(int(t), len(stops) - 2)
    return mix(stops[i], stops[i + 1], t - i)


def dist(p):
    r, c = POS[p]
    return math.hypot((c - CX) / 2, r - CY)


def scale(c, k):
    return tuple(int(v * k) for v in c)


# ---------------------------------------------------------------- static ---
def s_original():
    return ORIGINAL


def s_valentine():  # deep red top -> hot pink tip
    return {p: grad(["c8001e", "ff1a48", "ff4fa0"], POS[p][0] / 6) for p in PANELS}


def s_sunset():
    return {p: grad(["5a00b4", "e0207a", "ff6a00", "ffc400"], POS[p][0] / 6) for p in PANELS}


def s_rainbow():  # diagonal rainbow across the heart
    return {p: hsv((POS[p][1] + 2) / 9 * 0.85) for p in PANELS}


def s_ocean():
    random.seed(7)
    return {p: grad(["00e5ff", "0077ff", "1a00b4"], POS[p][0] / 6 + random.uniform(-.1, .1))
            for p in PANELS}


def s_aurora():
    return {p: grad(["00ff88", "00c8c8", "5a3cff", "c832ff"], (POS[p][1] + 2) / 8) for p in PANELS}


def s_fall():  # Thanksgiving / autumn
    random.seed(11)
    pal = ["ff5a00", "ff8c00", "c83200", "ffb000", "8b2500", "e06000"]
    return {p: random.choice(pal) for p in PANELS}


def s_christmas():
    return {p: ("ffffff" if p == 0 else ("ff0010" if (POS[p][0] + (POS[p][1] + 2) // 2) % 2 == 0
                                          else "00c828")) for p in PANELS}


def s_usa():
    return {p: ("ff0018" if POS[p][0] in (0, 3, 6) else "ffffff" if POS[p][0] in (1, 4)
                else "0020ff") for p in PANELS}


def s_candy():  # pastel
    pal = ["ffb3d9", "b3e0ff", "c8ffb3", "fff0b3", "e0b3ff", "ffd0b3"]
    return {p: pal[i % len(pal)] for i, p in enumerate(sorted(PANELS, key=lambda q: POS[q]))}


def s_warm():  # cozy warm white, slightly uneven like candles
    random.seed(3)
    return {p: mix("ff8a2a", "ffc070", random.random()) for p in PANELS}


def s_bullseye():  # rings from the centre
    return {p: ["ffffff", "ff1a48", "ff0080", "a000ff"][min(3, int(dist(p) * 1.3))] for p in PANELS}


STATIC = {k[2:]: v for k, v in globals().items() if k.startswith("s_")}


# ------------------------------------------------------------- animations ---
def a_heartbeat():
    """red heart, lub-dub pulse"""
    base = s_valentine()
    curve = [.25, .6, 1, .7, .4, .75, .95, .6, .4, .3, .27, .25, .25, .25, .25, .25]
    while True:
        for k in curve:
            yield {p: scale(bytes.fromhex(base[p]) if isinstance(base[p], str) else base[p], k)
                   for p in PANELS}, .09


def a_rainbow_wave():
    t = 0
    while True:
        yield {p: hsv(POS[p][1] / 10 + POS[p][0] / 20 - t) for p in PANELS}, .12
        t += .02


def a_ripple():
    t = 0
    while True:
        yield {p: hsv(.92 - dist(p) * .12 + t * .3,
                      1, .25 + .75 * (0.5 + 0.5 * math.cos(dist(p) * 2.2 - t * 4))) for p in PANELS}, .12
        t += .12


def a_chase():
    """comet running round the outline over a dim purple heart"""
    i = 0
    n = len(OUTLINE)
    while True:
        c = {p: (25, 0, 45) for p in PANELS}
        for k, b in enumerate((1, .45, .18)):
            c[OUTLINE[(i - k) % n]] = scale(hsv(i / n), b)
        yield c, .12
        i += 1


def a_twinkle():
    """starry night: dark blue with random white sparkles"""
    lvl = {p: 0.0 for p in PANELS}
    while True:
        for p in PANELS:
            lvl[p] *= .7
        for p in random.sample(PANELS, 2):
            lvl[p] = 1.0
        yield {p: mix((0, 10, 60), (255, 255, 255), lvl[p]) for p in PANELS}, .15


def a_fireplace():
    while True:
        yield {p: grad(["ffd040", "ff6a00", "c01800", "400000"],
                       POS[p][0] / 8 + random.uniform(0, .45)) for p in PANELS}, .15


def a_party():
    while True:
        yield {p: hsv(random.random()) for p in PANELS}, .5


def a_breathe():
    """original heart colours slowly breathing"""
    t = 0
    while True:
        k = .2 + .8 * (0.5 - 0.5 * math.cos(t))
        yield {p: scale(bytes.fromhex(ORIGINAL[p]), k) for p in PANELS}, .12
        t += .12


def a_christmas_twinkle():
    base = s_christmas()
    while True:
        c = {p: bytes.fromhex(base[p]) for p in PANELS}
        for p in random.sample(PANELS, 3):
            c[p] = (255, 220, 150)
        yield c, .4


LETTER_I = {17, 10, 9}                                   # column just left of centre, top to bottom
LETTER_U = {15, 16, 11, 9, 1, 2, 4, 6}                    # two straight sides + flat bottom (no tip)


def a_i_love_u():
    """I -> red heart (with a beat) -> U, slow crossfades, repeating"""
    white, red, off = (255, 255, 255), (255, 0, 20), (0, 0, 0)
    I = {p: red if p in LETTER_I else white for p in PANELS}    # red I on white
    H = {p: red for p in PANELS}
    U = {p: red if p in LETTER_U else white for p in PANELS}    # red U on white
    dark = {p: off for p in PANELS}
    I_only = {p: red if p in LETTER_I else off for p in PANELS}  # I with the white turned off
    U_only = {p: red if p in LETTER_U else off for p in PANELS}  # U with the white turned off
    step = .08

    def fade(a, b, secs=1.6):
        """Panels that change colour fade out then fade in (no RGB blending:
        white<->red blends look yellow on these panels). Unchanged panels hold."""
        n = int(secs / step)
        for i in range(1, n + 1):
            t = i / n
            out = {}
            for p in PANELS:
                if a[p] == b[p]:
                    out[p] = a[p]
                elif t < .5:
                    k = 1 - t * 2
                    out[p] = scale(a[p], k * k)          # ease out
                else:
                    k = t * 2 - 1
                    out[p] = scale(b[p], k * k)          # ease in
            yield out, step

    def hold(a, secs):
        yield a, secs

    while True:                                   # instant switches (user preference)
        yield from hold(I, 2)
        yield from hold(I_only, 1.5)
        yield from hold(H, .6)
        for k in (1, .55, 1, .45, .3, .45, 1, .55, 1, .45):   # gentle lub-dub x2
            yield {p: scale(red, .55 + .45 * k) for p in PANELS}, .13
        yield from hold(H, 1.5)
        yield from hold(U_only, 1.5)
        yield from hold(U, 2)
        yield from hold(dark, .8)


def a_i_love_u_red():
    """I -> heart -> U in red only, no white background, instant switches"""
    red, off = (255, 0, 20), (0, 0, 0)
    I_only = {p: red if p in LETTER_I else off for p in PANELS}
    U_only = {p: red if p in LETTER_U else off for p in PANELS}
    H = {p: red for p in PANELS}
    dark = {p: off for p in PANELS}
    while True:
        yield I_only, 3
        yield H, .6
        for k in (1, .55, 1, .45, .3, .45, 1, .55, 1, .45):   # gentle lub-dub x2
            yield {p: scale(red, .55 + .45 * k) for p in PANELS}, .13
        yield H, 1.5
        yield U_only, 3
        yield dark, .8


ANIM = {k[2:]: v for k, v in globals().items() if k.startswith("a_")}


# ------------------------------------------------------------------ main ---
def stop_running():
    """Any running animation (in HA's container or elsewhere) sees the token
    change on its next frame and exits."""
    open(RUNFILE, "w").write("stop")
    # also kill any other heart.py process in this container (covers old versions)
    me = os.getpid()
    for d in os.listdir("/proc"):
        if not d.isdigit() or int(d) == me:
            continue
        try:
            cmd = open(f"/proc/{d}/cmdline", "rb").read().split(b"\0")
        except OSError:
            continue
        if any(a.endswith(b"heart.py") for a in cmd) and b"python3" in cmd[0]:
            try:
                os.kill(int(d), signal.SIGTERM)
            except OSError:
                pass


def run_anim(gen, seconds):
    token = "%d-%f" % (os.getpid(), time.time())
    open(RUNFILE, "w").write(token)
    if os.fork():           # parent returns at once so HA's shell_command finishes
        return
    os.setsid()
    if os.fork():
        os._exit(0)
    fd = os.open(os.devnull, os.O_RDWR)
    for f in (0, 1, 2):
        os.dup2(fd, f)
    end = time.time() + seconds if seconds else None
    try:
        for colors, delay in gen():
            try:
                if open(RUNFILE).read() != token:
                    break
            except OSError:
                break
            show(colors)
            time.sleep(delay)
            if end and time.time() > end:
                break
    finally:
        os._exit(0)


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "list"
    secs = float(sys.argv[2]) if len(sys.argv) > 2 else 0
    if name == "list":
        print("static:", " ".join(STATIC))
        print("animated:", " ".join(ANIM))
        return
    stop_running()
    if name == "stop":
        return
    if name.startswith("govee:"):
        # built-in/custom Govee effect over LAN (govee_scene.py); exit 2 if unknown
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import govee_scene
        if govee_scene.send(IP, name[6:]) is None:
            sys.exit(2)
        return
    power_on()
    if name in STATIC:
        show(STATIC[name]())
    elif name in ANIM:
        run_anim(ANIM[name], secs)
    else:
        sys.exit(f"unknown scene {name}")


if __name__ == "__main__":
    main()
