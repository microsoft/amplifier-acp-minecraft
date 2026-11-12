"""Disposable packaged-client verification. No production home/model/server."""
import argparse
import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


async def verify(root, source):
    manifest=json.loads((root/'manifest.json').read_text())
    node=root/manifest['commands']['node']
    python=root/manifest['commands']['python']
    env={**os.environ,'PYTHONNOUSERSITE':'1','PYTHONDONTWRITEBYTECODE':'1',
         'PLAYWRIGHT_BROWSERS_PATH':str(root/'browsers'),'RUN_SCREENSHOT_RENDER':'1',
         'WORKSHOP_TEST_PYTHON':str(python)}
    subprocess.run([str(python),'-I',str(root/'launch.py'),'doctor'],env=env,check=True)
    subprocess.run([str(python),'-s',str(root/'app/adapter.py'),'--help'],env=env,check=True,timeout=30)
    sys.path.insert(0,str(root/'app'))
    from installation_session_probe import probe
    with tempfile.TemporaryDirectory(prefix='Minecraft package fixture ') as temporary:
        home=Path(temporary);(home/'app').mkdir()
        # Exercise the fixed launcher in a spaced home without joining a server.
        (home/'config.json').write_text('{}')
        offline=home/'installation-connections';offline.mkdir()
        intent={'schema':1,'phase':'disconnected','request_id':'preserved-fixture'}
        (offline/'state.json').write_text(json.dumps(intent))
        before_files={str(p.relative_to(home)):p.read_bytes() for p in home.rglob('*') if p.is_file()}
        exited=subprocess.run([str(python),'-I',str(root/'launch.py'),'body','--home',str(home)],env=env,check=False,capture_output=True,text=True,timeout=90)
        assert exited.returncode==0, {'code':exited.returncode,'stdout':exited.stdout,'stderr':exited.stderr}
        assert 'disconnected' in exited.stdout
        assert {str(p.relative_to(home)):p.read_bytes() for p in home.rglob('*') if p.is_file()}==before_files

        for name in ('acp_client.py','prompt_lifecycle.py'):
            shutil.copy2(root/'app'/name,home/'app'/name)
        peer=home/'peer.py';shutil.copy2(source/'tests/session_probe_fixture.py',peer)
        log=home/'events.jsonl'
        cfg={'control_port':1,'token':'disposable-not-a-live-secret'}
        endpoint={'command':[str(python),str(peer)],'cwd':str(home),'env':{'PROBE_LOG':str(log)}}
        (home/'config.json').write_text(json.dumps(cfg));(home/'endpoint.json').write_text(json.dumps(endpoint))
        effective={**endpoint,'mcp_servers':[{'type':'http','name':'minecraft','url':'http://127.0.0.1:1/mcp',
                    'headers':[{'name':'Authorization','value':'Bearer disposable-not-a-live-secret'}]}]}
        saved={'session':'original-fixture-session','binding':hashlib.sha256(json.dumps(effective,sort_keys=True).encode()).hexdigest()}
        binding=home/'session.json';binding.write_text(json.dumps(saved));before=binding.read_bytes()
        loaded=await probe(home,30)
        assert loaded['saved_session_loaded'] and binding.read_bytes()==before
        assert [json.loads(line) for line in log.read_text().splitlines()]==[{'action':'initialize'},{'action':'load','session':'original-fixture-session'}]
        binding.unlink();log.unlink()
        empty=await probe(home,30)
        assert empty['initialized'] and not empty['saved_session_loaded'] and not binding.exists()
        assert [json.loads(line) for line in log.read_text().splitlines()]==[{'action':'initialize'}]
    # Fixture tests resolve production modules relative to the bundle, including
    # the real packaged Chromium renderer. They are removed after verification.
    fixtures=root/'app/tests'
    try:
        shutil.copytree(source/'tests',fixtures)
        subprocess.run([str(node),'--test',*[str(fixtures/name) for name in
            ('body-chat.test.cjs','body-gather.test.cjs','body-timeout.test.cjs','activity-review.test.cjs','screenshots.test.cjs')]],env=env,check=True)
    finally:
        shutil.rmtree(fixtures,ignore_errors=True)
    result={'target':manifest['target'],'source_commit':manifest['source_commit'],'official_sdk':manifest['sdk_commit'],
            'original_session_loaded':True,'unused_initialize_only':True,'game_server':False,'model_prompts':0,
            'body_fixtures':True,'actual_packaged_browser':True,'controller_entrypoint_imports':True,'offline_body_launcher_no_join':True,'native_service_lifecycle_verified':False}
    print(json.dumps(result))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--bundle',type=Path,required=True);p.add_argument('--source',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True)
    a=p.parse_args();a.receipt.write_text(json.dumps(asyncio.run(verify(a.bundle.resolve(),a.source.resolve())),indent=2)+'\n')
