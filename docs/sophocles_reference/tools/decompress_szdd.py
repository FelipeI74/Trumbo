from pathlib import Path
import struct, sys

def decompress_szdd(src: bytes) -> bytes:
    if src[:8] != b'SZDD\x88\xf0\x27\x33':
        raise ValueError('not SZDD')
    out_size = struct.unpack_from('<I', src, 10)[0]
    ip=14
    win=bytearray(b' '*4096)
    r=4096-16
    out=bytearray()
    while ip < len(src) and len(out) < out_size:
        flags=src[ip]; ip+=1
        for bit in range(8):
            if len(out)>=out_size or ip>=len(src): break
            if flags & (1<<bit):
                c=src[ip]; ip+=1
                out.append(c); win[r]=c; r=(r+1)&0xfff
            else:
                if ip+1>=len(src): break
                b1=src[ip]; b2=src[ip+1]; ip+=2
                pos=b1 | ((b2 & 0xf0)<<4)
                ln=(b2 & 0x0f)+3
                for k in range(ln):
                    c=win[(pos+k)&0xfff]
                    out.append(c); win[r]=c; r=(r+1)&0xfff
                    if len(out)>=out_size: break
    if len(out)!=out_size:
        print(f'warning output {len(out)} expected {out_size}', file=sys.stderr)
    return bytes(out)

if __name__=='__main__':
    inp=Path(sys.argv[1]); out=Path(sys.argv[2])
    out.write_bytes(decompress_szdd(inp.read_bytes()))
