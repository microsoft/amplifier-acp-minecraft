"""Actual pure helper fixtures; no ACP session, provider or model invocation."""
import json
import subprocess
import tempfile
from pathlib import Path


def verify(binary):
    with tempfile.TemporaryDirectory(prefix='Minecraft pure helper ') as temporary:
        folder=Path(temporary)
        def run(command,value,watch=False,valid=True):
            source=folder/'input.json';source.write_text(json.dumps(value))
            argv=[str(binary),command]
            if watch:
                argv+=['--store',str(folder/'watch.json')]
            result=subprocess.run(argv+[str(source)],cwd=folder,capture_output=True,text=True,timeout=15)
            if valid:
                if result.returncode:
                    raise ValueError('Pure helper failed: '+result.stderr)
                return json.loads(result.stdout)
            if result.returncode==0:
                raise ValueError('Helper incorrectly accepted an unknown bound')
        unbounded={'kind':'no_configured_bound'}
        continuation={'status':'running','remaining_ms':unbounded,'remaining_turns':unbounded,'minimum_turn_ms':120000,'idle':True,'observation_current':True,'receipts_complete':True,'actions_succeeded':True,'recovery_attempts':0}
        assert run('continuation-v2',continuation)['action']=='continue'
        assert run('continuation-v2',{**continuation,'status':'stopped'})['action']!='continue'
        run('continuation-v2',{**continuation,'remaining_ms':None},valid=False)
        watch={'scope':'native-package-fixture','task':{'id':'original-fixture','goal':'Existing test responsibility','status':'waiting','deadline_ms':unbounded,'remaining_turns':{'kind':'finite','value':4}},'events':[],
               'action':{'operation':'arm','spec':{'label':'Changed fact','condition':'Peer supplies a review','kinds':['message'],'ttl_seconds':300}}}
        created=run('watch-v2',watch,watch=True)['watch']
        assert created['expires_ms']-created['created_ms']==300000
        before=(folder/'watch.json').read_bytes()
        run('watch-v2',{**watch,'task':{**watch['task'],'deadline_ms':None}},watch=True,valid=False)
        assert (folder/'watch.json').read_bytes()==before
        listing=run('watch-v2',{**watch,'action':{'operation':'list'}},watch=True)
        assert listing['watches'][0]==created and listing['calls_this_hour']==0
    return {'continuation_v2':True,'watch_v2':True,'stop_preserved':True,'unknown_bound_refused':True,'store_preserved':True,'model_calls':0,'engine_selected':False}
