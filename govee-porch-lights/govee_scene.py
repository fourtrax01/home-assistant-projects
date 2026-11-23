# usage: govee_scene.py [--sku H7076] IP "<effect name>" [param_hex]   (Govee built-in effects over LAN ptReal)
#        govee_scene.py [--sku H7076] list
# H6069 heart (default sku), decoded from a Govee-app BLE capture 2026-11-22:
#   a3 00 01 <nframes> + param[0:15] (param[0] 0x50 -> 0x58), a3 01.. +17 bytes, last a3 ff; xor checksum
#   then 33 05 04 <code lo> <code hi> <param[12]> <param[1]>
# H7076 porch (tested 2026-11-22): same a3 framing with the library param UNCHANGED, then
#   33 05 04 <code lo> <code hi> (no tail). Scenes with an empty param (Rainbow, White Light...) = commit only.
# Effects live in h6069_effects.json / h7076_effects.json (custom ones like the heart's "Candy Cane" too).
# H7076 custom colors: recolor(param, {old: new}) (tested 11-22: Christmas -> blue/white = "Blue & White").
# Name matching ignores case, spaces and punctuation ("fathers_day" = "Father's Day"); prefix match as fallback.
import socket, json, base64, sys, os, re
HERE=os.path.dirname(os.path.abspath(__file__))
_LIBS={}
def lib(sku='H6069'):
    if sku not in _LIBS: _LIBS[sku]=json.load(open(os.path.join(HERE,f'{sku.lower()}_effects.json')))
    return _LIBS[sku]
LIB=lib()
# two H6069 "0b" effects: app sent param[12]=01 and a special commit tail
SPECIAL={0x4703:bytes.fromhex('0b4006400664'), 0x46f0:bytes.fromhex('0064')}
def frame(b):
    b=bytes(b)+bytes(19-len(b)); cs=0
    for x in b: cs^=x
    return b+bytes([cs])
def _a3(p):
    chunks=[p[15:][i:i+17] for i in range(0,len(p)-15,17)]
    fr=[frame(bytes([0xa3,0,1,1+len(chunks)])+p[:15])]
    for i,c in enumerate(chunks): fr.append(frame(bytes([0xa3,0xff if i==len(chunks)-1 else i+1])+c))
    return fr
def build(code,p,sku='H6069'):
    p=bytearray(p)
    if sku=='H7076':
        return (_a3(p) if p else [])+[frame(bytes([0x33,5,4,code&0xff,code>>8]))]
    p[0]=0x58
    if code in SPECIAL: p[12]=1
    tail=SPECIAL.get(code, bytes([p[12],p[1]]))
    return _a3(p)+[frame(bytes([0x33,5,4,code&0xff,code>>8])+tail)]
def scene_colors(p):
    """H7076 param: 0a <nlayers>, each layer <len> ...; color count at layer offset 16, then RGB*n.
    Returns [(offset, [rgb_hex, ...]), ...] per layer (parses all 73 non-empty H7076 scenes)."""
    out=[]; i=2
    for _ in range(p[1]):
        L=p[i]; n=p[i+16]
        out.append((i+17,[bytes(p[i+17+3*k:i+20+3*k]).hex() for k in range(n)])); i+=1+L
    if i!=len(p): raise ValueError('unexpected layout')
    return out
def scene_palette(name, sku='H7076', maxn=3):
    """Up to maxn distinct, non-dark colors from a scene (for matching the eaves).
    Layers whose color list doesn't fit inside the layer are skipped (some scenes, e.g.
    Halloween, use another layout there)."""
    e=find(name,sku)
    if not e or not e['param']: return []
    p=bytes.fromhex(e['param'])
    try: layers=scene_colors(p)
    except (ValueError,IndexError): return []
    out=[]; i=2
    for off,cs in layers:
        L=p[i]; i+=1+L
        if off-17+17+3*len(cs) > off-17+1+L: continue      # list runs past the layer
        for c in cs:
            r,g,b=bytes.fromhex(c)
            if max(r,g,b) < 60: continue
            if any(sum(abs(x-y) for x,y in zip((r,g,b),bytes.fromhex(o))) < 90 for o in out): continue  # near-duplicate
            out.append(c)
            if len(out)==maxn: return out
    return out
def recolor(param_hex, mapping):
    """H7076: replace colors in a scene param, mapping {'ff0000': '0000ff', ...}."""
    p=bytearray.fromhex(param_hex)
    for off,cs in scene_colors(p):
        for k,c in enumerate(cs): p[off+3*k:off+3*k+3]=bytes.fromhex(mapping.get(c,c))
    return p.hex()
def norm(s): return re.sub(r'[^a-z0-9]','',s.lower())
def find(name,sku='H6069'):
    n=norm(name)
    for v in lib(sku):
        if norm(v['name'])==n: return v
    for v in lib(sku):
        if norm(v['name']).startswith(n): return v
    return None
def frames_for(name,sku='H6069',param_hex=None):
    e=find(name,sku)
    if not e: return None
    p=bytes.fromhex(param_hex if param_hex is not None else e['param'])
    return [frame(bytes.fromhex('330101'))]+build(e['code'],p,sku)
def send_frames(ip,fr):
    s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    s.sendto(json.dumps({"msg":{"cmd":"ptReal","data":{"command":[base64.b64encode(f).decode() for f in fr]}}}).encode(),(ip,4003))
def send(ip,name,param_hex=None,sku='H6069'):
    fr=frames_for(name,sku,param_hex)
    if fr: send_frames(ip,fr)
    return fr
if __name__=='__main__':
    a=sys.argv[1:]; sku='H6069'
    if a[:1]==['--sku']: sku=a[1].upper(); a=a[2:]
    if a[0]=='list':
        for v in lib(sku): print(f"{v['name']:20} {v['code']:#06x}")
        sys.exit()
    fr=send(a[0],a[1],a[2] if len(a)>2 else None,sku)
    if fr is None: sys.exit(f"unknown effect {a[1]}")
    for f in fr: print(f.hex())
