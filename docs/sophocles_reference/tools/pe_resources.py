import struct, json, sys
from pathlib import Path

def parse_pe_resources(path):
    data=Path(path).read_bytes()
    peoff=struct.unpack_from('<I',data,0x3c)[0]
    if data[peoff:peoff+4]!=b'PE\0\0': raise ValueError('not PE')
    coff=peoff+4
    machine,nsects,tstamp,ptrsym,nsym,sizeopt,chars=struct.unpack_from('<HHIIIHH',data,coff)
    opt=coff+20
    magic=struct.unpack_from('<H',data,opt)[0]
    dd=opt+(96 if magic==0x10b else 112)
    res_rva,res_size=struct.unpack_from('<II',data,dd+2*8)
    sec_off=opt+sizeopt
    sects=[]
    for i in range(nsects):
        off=sec_off+i*40
        name=data[off:off+8].rstrip(b'\0').decode('ascii','replace')
        vsize,vaddr,rawsize,rawptr=struct.unpack_from('<IIII',data,off+8)
        sects.append((name,vaddr,vsize,rawptr,rawsize))
    def rva2off(rva):
        for name,va,vs,rp,rs in sects:
            if va<=rva<va+max(vs,rs): return rp+(rva-va)
        raise ValueError(hex(rva))
    base=rva2off(res_rva)
    def read_name(v):
        if v & 0x80000000:
            noff=base+(v&0x7fffffff); ln=struct.unpack_from('<H',data,noff)[0]
            return data[noff+2:noff+2+ln*2].decode('utf-16le','replace')
        return v
    leaves=[]
    def walk(rel,path):
        o=base+rel
        _,_,_,_,nn,ni=struct.unpack_from('<IIHHHH',data,o)
        for j in range(nn+ni):
            no,dv=struct.unpack_from('<II',data,o+16+j*8)
            name=read_name(no)
            if dv&0x80000000: walk(dv&0x7fffffff,path+[name])
            else:
                de=base+(dv&0x7fffffff)
                rva,size,cp,_=struct.unpack_from('<IIII',data,de)
                fo=rva2off(rva)
                leaves.append({'path':path+[name],'rva':rva,'file_offset':fo,'size':size,'codepage':cp,'data':data[fo:fo+size]})
    walk(0,[])
    return leaves

def decode_string_table(blob, block_id):
    # each block = 16 UTF16 strings, resource id = (block_id-1)*16 + index
    out=[]; pos=0
    for i in range(16):
        if pos+2>len(blob): break
        n=struct.unpack_from('<H',blob,pos)[0]; pos+=2
        raw=blob[pos:pos+n*2]; pos+=n*2
        if n:
            out.append(((int(block_id)-1)*16+i,raw.decode('utf-16le','replace')))
    return out

if __name__=='__main__':
    leaves=parse_pe_resources(sys.argv[1])
    print('leaves',len(leaves))
    from collections import Counter
    print(Counter(str(x['path'][0]) for x in leaves))
    strings=[]
    for x in leaves:
        if x['path'][0]==6 and len(x['path'])>=2 and isinstance(x['path'][1],int):
            strings += decode_string_table(x['data'],x['path'][1])
    for rid,s in strings:
        print(f'{rid}\t{s}')
