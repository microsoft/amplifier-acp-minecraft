"""Operator-only console helper; never exposed through agent tools."""
import argparse,socket,struct
from pathlib import Path
def command(properties,cmd):
    cfg=dict(line.strip().split('=',1) for line in Path(properties).read_text().splitlines() if '=' in line and not line.startswith('#'))
    def read_exact(s,n):
        data=b''
        while len(data)<n:
            part=s.recv(n-len(data))
            if not part:raise RuntimeError('RCON disconnected')
            data+=part
        return data
    def receive(s):
        n=struct.unpack('<i',read_exact(s,4))[0];return read_exact(s,n)
    def send(s,id,kind,text):
        b=struct.pack('<ii',id,kind)+text.encode()+b'\0\0';s.sendall(struct.pack('<i',len(b))+b)
    with socket.create_connection(('127.0.0.1',int(cfg['rcon.port'])),timeout=10) as s:
        send(s,1,3,cfg['rcon.password']);r=receive(s)
        if struct.unpack('<i',r[:4])[0]==-1:raise RuntimeError('RCON authentication failed')
        send(s,2,2,cmd);r=receive(s);return r[8:-2].decode()
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--properties',required=True);p.add_argument('command');a=p.parse_args();print(command(a.properties,a.command))
