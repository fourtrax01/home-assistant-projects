# usage: govee_panels.py IP "idx:RRGGBB" ...   (H6069 per-panel colors over LAN ptReal)
import socket, json, base64, sys
ip=sys.argv[1]; ents=[a.split(':') for a in sys.argv[2:]]
def frame(b):
    b=bytes(b)+bytes(19-len(b)); cs=0
    for x in b: cs^=x
    return b+bytes([cs])
data=bytearray()
for i,c in ents: data+=bytes([1])+bytes.fromhex(c)+bytes([int(i)])
chunks=[]
first=data[:7]; rest=data[7:]
while rest: chunks.append(rest[:17]); rest=rest[17:]
npk=1+max(1,len(chunks))
frames=[frame(b'\xa3\x00'+bytes([1,npk,3,0,0,0,0,0,0,len(ents)])+first)]
for n,c in enumerate(chunks):
    frames.append(frame(bytes([0xa3, 0xff if n==len(chunks)-1 else n+1])+c))
if not chunks: frames.append(frame(b'\xa3\xff'))

frames.append(frame(bytes.fromhex('33050a2003')))
for f in frames: print(f.hex())
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
s.sendto(json.dumps({"msg":{"cmd":"ptReal","data":{"command":[base64.b64encode(f).decode() for f in frames]}}}).encode(),(ip,4003))
