#!/usr/bin/env python3
"""
Describe a camera snapshot for a push notification.

Tries the local Ollama vision model first (fast, free, private), then falls
back to Gemini's API if the PC is off or the model is unavailable. Prints the
description to stdout, or nothing at all if every provider fails -- the
automation then uses its "Activity detected." fallback.

Reasons for failure go to stderr so they show up in the automation trace.

Usage: describe_image.py <image_path>
"""
import sys
import json
import time
import base64
import re
import socket
import urllib.request
import urllib.error

snap_file = sys.argv[1]

# Written defensively: small vision models confabulate plausible detail on dark,
# low-contrast night frames (invented packages and parked cars, in practice).
# The rules below are ordered worst-offender first.
PROMPT = (
    "You are writing a push notification for a home security camera. "
    "Report ONLY what is plainly visible in this image. "
    "Do not guess, infer, or describe anything you cannot actually see. "
    "If there is no person, package, or vehicle, do not mention those things at all -- "
    "instead reply with the single sentence: Nothing notable; the porch is empty. "
    "If a person IS visible, describe them: how many, what they are wearing, and what "
    "they are doing (approaching, leaving, looking around, pressing the doorbell, "
    "carrying or dropping something). "
    "If the person is dropping off or carrying a package, call them a delivery driver. "
    "Ignore any timestamp, date, or camera name overlaid on the image. "
    "Be concise: at most 2 sentences. No emojis, no quotes, no speculation."
)

OLLAMA_HOST = "192.168.1.90"
OLLAMA_PORT = 11434
OLLAMA_URL = f"http://{OLLAMA_HOST}:{OLLAMA_PORT}/api/generate"
OLLAMA_MODEL = "qwen2.5vl:7b"
# Warm model answers in ~1-3s. The ceiling covers a cold load from disk.
OLLAMA_TIMEOUT = 25
# If the PC is off, the firewall drops SYNs and a plain request would burn the
# full OLLAMA_TIMEOUT before Gemini ever gets a turn. Probe the socket first.
OLLAMA_CONNECT_TIMEOUT = 1.5

GEMINI_KEY_FILE = "/config/.gemini_key"
GEMINI_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-flash-lite-latest",
    "gemini-2.5-flash",
]
GEMINI_PER_CALL_TIMEOUT = 10
GEMINI_BUDGET = 20
# Home Assistant kills a shell_command after 60 s. Captions, carrier follow-ups and
# the Gemini fallback all have to fit in this budget, measured from the start.
TOTAL_BUDGET = 50
START = time.time()


def left():
    """Seconds remaining in TOTAL_BUDGET."""
    return START + TOTAL_BUDGET - time.time()


def log(msg):
    print(msg, file=sys.stderr)


def post_json(url, payload, timeout, headers=None):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers=headers or {"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def ollama_reachable():
    try:
        socket.create_connection(
            (OLLAMA_HOST, OLLAMA_PORT), OLLAMA_CONNECT_TIMEOUT
        ).close()
        return True
    except OSError as e:
        log(f"ollama: unreachable ({type(e).__name__}), skipping to fallback")
        return False


def try_ollama(img_b64):
    if not ollama_reachable():
        return None
    t = time.time()
    try:
        data = post_json(
            OLLAMA_URL,
            {
                "model": OLLAMA_MODEL,
                "prompt": PROMPT,
                "images": [img_b64],
                "stream": False,
                # num_ctx must match Frigate's genai provider_options: Ollama keys the
                # loaded runner by context size, so a mismatch reloads the model on
                # every alternating request instead of answering from the warm one.
                "options": {"num_predict": 150, "temperature": 0, "num_ctx": 16384},
            },
            min(OLLAMA_TIMEOUT, max(1, left())),
        )
    except Exception as e:
        log(f"ollama: {type(e).__name__}: {e}")
        return None

    text = (data.get("response") or "").strip()
    if not text:
        log(f"ollama: empty response: {json.dumps(data)[:200]}")
        return None
    log(f"ollama: ok in {time.time() - t:.1f}s")
    return " ".join(text.split())[:500]


def try_gemini(img_b64):
    try:
        with open(GEMINI_KEY_FILE) as f:
            api_key = f.read().strip()
    except OSError as e:
        log(f"gemini: no key: {e}")
        return None

    payload = {
        "contents": [{
            "parts": [
                {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}},
                {"text": PROMPT},
            ]
        }],
        "generationConfig": {"temperature": 0},
    }
    deadline = min(time.time() + GEMINI_BUDGET, START + TOTAL_BUDGET)

    for model in GEMINI_MODELS:
        if time.time() >= deadline:
            log("gemini: out of time budget")
            return None
        # Key goes in a header, not the URL, so it can't leak into logs or error messages.
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent"
        )
        timeout = min(GEMINI_PER_CALL_TIMEOUT, deadline - time.time())
        if timeout < 2:
            log("gemini: out of time budget")
            return None
        try:
            data = post_json(url, payload, timeout,
                             {"Content-Type": "application/json", "x-goog-api-key": api_key})
        except urllib.error.HTTPError as e:
            body = e.read()[:150].decode(errors="replace").replace("\n", " ")
            log(f"gemini: {model} HTTP {e.code} {body}")
            if e.code == 429 or e.code >= 500:
                continue
            return None
        except Exception as e:
            log(f"gemini: {model} {type(e).__name__}: {e}")
            continue

        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except (KeyError, IndexError):
            log(f"gemini: {model} no candidate: {json.dumps(data)[:150]}")
            continue
        if text:
            log(f"gemini: {model} ok")
            return " ".join(text.split())[:500]

    return None


COLOR_PROMPT = (
    "Question 1: is this person a delivery driver (holding, scanning, placing or carrying "
    "a package or parcel)? Question 2: what colors is the vest, jacket, hoodie or shirt on "
    "their upper body? Reply with yes or no, a comma, then the colors you actually see."
)


def carrier_from_colors(upper, caption=""):
    """upper = the follow-up's upper-body colors; caption adds context (not for brown,
    since brown pants are common on Amazon drivers)."""
    u = upper.lower()
    c = u + " " + caption.lower()
    if "purple" in c and "orange" in c:
        return "FedEx"
    # USPS: light-blue / blue-gray shirt (navy bottoms), often a sun helmet. Checked
    # before Amazon so "light blue shirt, navy shorts" isn't read as blue-and-black.
    cap = caption.lower()
    if any(k in c for k in ("light blue", "blue-gray", "blue gray", "grey-blue", "gray-blue", "pale blue", "sky blue")) \
            or any(k in cap for k in ("postal", "mail carrier", "mailman", "pith helmet", "sun helmet")):
        return "USPS"
    if "teal" in c or ("blue" in c and "black" in c):
        return "Amazon"
    if "yellow" in u and "red" in u:
        return "DHL"
    if "brown" in u:
        return "UPS"
    # UPS seasonal drivers wear a dark vest with yellow reflective stripes.
    if "yellow" in u and ("black" in u or "dark" in u):
        return "UPS"
    return None


DRIVEWAY_URL = "http://192.168.1.91:5000/api/driveway/latest.jpg"  # Frigate (driveway camera)
TRUCK_PROMPT = (
    "This is a view of a residential street. Is there a delivery truck or van parked or driving "
    "on the street? Reply in one line: its color, markings and type (for example: brown box truck), or none."
)


def truck_carrier():
    """The delivery truck is rarely in the doorbell frame, but the driveway camera
    sees the street. Crop to the street band (the full wide frame is too small for
    the 7B model) and map the truck's color: brown = UPS, purple/orange = FedEx.
    Needs Pillow (present in the HA core container); skips quietly otherwise."""
    if left() < 8:
        log("truck: skipped, out of time budget")
        return None
    try:
        import io
        from PIL import Image
        with urllib.request.urlopen(DRIVEWAY_URL, timeout=min(4, left())) as r:
            im = Image.open(io.BytesIO(r.read())).convert("RGB")
        w, h = im.size
        crop = im.crop((int(w * 0.40), int(h * 0.24), w, int(h * 0.58)))
        crop = crop.resize((crop.width * 2, crop.height * 2))
        buf = io.BytesIO()
        crop.save(buf, "JPEG", quality=90)
        data = post_json(
            OLLAMA_URL,
            {
                "model": OLLAMA_MODEL,
                "prompt": TRUCK_PROMPT,
                "images": [base64.b64encode(buf.getvalue()).decode()],
                "stream": False,
                "options": {"num_predict": 30, "temperature": 0, "num_ctx": 16384},
            },
            min(OLLAMA_TIMEOUT, max(1, left())),
        )
    except Exception as e:
        log(f"truck: {type(e).__name__}: {e}")
        return None
    t = (data.get("response") or "").strip().lower()
    name = None
    if "brown" in t:
        name = "UPS"
    elif "mail" in t or "postal" in t or "usps" in t or ("white" in t and "red" in t and "blue" in t):
        name = "USPS"
    elif "purple" in t or "orange" in t:
        name = "FedEx"
    log(f"truck: {t[:60]!r} -> {name}")
    return name


def add_carrier(text, img_b64):
    """The 7B model won't reliably name a carrier itself (it either refuses or says
    Amazon for everyone), so for deliveries ask only for the top's colors and map
    them to a carrier here. If it matches, name the carrier and drop the clothing
    description."""
    low = text.lower()
    if not any(w in low for w in ("person", "driver", "man", "woman", "someone", "people")):
        return text
    if left() < 10:
        log("carrier: skipped, out of time budget")
        return text
    try:
        data = post_json(
            OLLAMA_URL,
            {
                "model": OLLAMA_MODEL,
                "prompt": COLOR_PROMPT,
                "images": [img_b64],
                "stream": False,
                "options": {"num_predict": 70, "temperature": 0, "num_ctx": 16384},
            },
            min(OLLAMA_TIMEOUT, max(1, left())),
        )
    except Exception as e:
        log(f"carrier: {type(e).__name__}: {e}")
        return text
    answer = " ".join((data.get("response") or "").split())
    delivering = answer.lower().startswith("yes") or "delivery driver" in low
    # Colors: what the follow-up saw plus what the caption already says.
    colors = answer.split(",", 1)[1] if "," in answer else answer
    name = (truck_carrier() or carrier_from_colors(colors, text)) if delivering else None
    log(f"carrier: {answer[:200]!r} -> {name}")
    if not name:
        return text
    # Drop the clothing phrase ("in a blue vest", "wearing a dark hoodie and jeans").
    text = re.sub(
        r"\s*,?\s*(?:in|wearing)\s+(?:an?\s+)?[^,.]*?(?:vest|uniform|hoodie|jacket|shirt|t-shirt|top|clothing|outfit|pants|jeans|shorts)(?:\s+and\s+[^,.]*?(?:pants|jeans|shorts|cap|hat))?",
        "", text, count=1)
    art = "An" if name == "Amazon" else "A"
    new, n = re.subn(r"\b(?:A|a) (?:delivery driver|delivery person|person)\b", f"{art} {name} driver", text, count=1)
    if n:
        return new[0].upper() + new[1:]
    return f"{name} delivery: {text}"


def main():
    with open(snap_file, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    text = try_ollama(img_b64)
    if text:
        return add_carrier(text, img_b64)
    return try_gemini(img_b64)


try:
    result = main()
except Exception as e:
    log(f"describe: {type(e).__name__}: {e}")
    result = None

if result:
    print(result)
