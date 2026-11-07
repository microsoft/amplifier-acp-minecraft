#!/usr/bin/env python3
"""Protocol-2 Minecraft source/dependency provider. No service or game calls.

This fixed owner helper stages tested source before idle, then exchanges only
enrolled code/environment paths under an already-ready lifecycle participant.
"""
import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import tarfile
import uuid
import time
from pathlib import Path

from installation_guard import ContinuityError, digest, durable_write, installation_lock, read

REPOSITORY = 'microsoft/amplifier-acp-minecraft'
SDK_URL = 'https://github.com/agentclientprotocol/python-sdk.git'


def run(argv, **kwargs):
    return subprocess.check_output(argv, timeout=480, **kwargs)


def sync_directories(*directories):
    for directory in set(map(Path,directories)):
        fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)


def fingerprint(path):
    """Include dependency bytes and link targets, excluding only Python caches."""
    path = Path(path)
    if path.is_symlink():
        return digest({'link':os.readlink(path), 'contents':fingerprint(path.resolve())})
    if not path.is_dir():
        raise ContinuityError('Expected installed source/environment directory')
    files = {}
    for entry in sorted(path.rglob('*')):
        rel = entry.relative_to(path)
        if '__pycache__' in rel.parts or entry.suffix == '.pyc':
            continue
        if entry.is_symlink():
            files[str(rel)] = {'link':os.readlink(entry)}
        elif entry.is_file():
            files[str(rel)] = {'sha256':hashlib.sha256(entry.read_bytes()).hexdigest(),
                               'executable':bool(entry.stat().st_mode & 0o111)}
    return digest(files)


def sdk_pin(app):
    lines = [s.strip() for s in (app/'requirements.txt').read_text().splitlines() if s.strip() and not s.startswith('#')]
    pattern = r'agent-client-protocol @ git\+https://github.com/agentclientprotocol/python-sdk\.git@([0-9a-f]{40})'
    match = re.fullmatch(pattern, lines[0]) if len(lines)==1 else None
    if not match:
        raise ContinuityError('Source must pin the official Python SDK immutable commit')
    return match[1]


def verify_sdk(venv, app):
    commit=sdk_pin(app)
    # Read installed metadata directly, without importing packages or prompting.
    metadata = list(venv.glob('lib/python*/site-packages/agent_client_protocol-*.dist-info/direct_url.json'))
    if len(metadata) != 1:
        raise ContinuityError('One official SDK installation required')
    direct = read(metadata[0]);vcs = direct.get('vcs_info',{})
    if direct.get('url') != SDK_URL or vcs.get('commit_id') != commit or vcs.get('vcs') != 'git' or direct.get('dir_info',{}).get('editable'):
        raise ContinuityError('SDK immutable upstream provenance mismatch')
    return {'commit':commit, 'direct_url':direct}


class Provider:
    def __init__(self, cfg):
        self.c = cfg
        self.root, self.home = Path(cfg['state']), Path(cfg['home'])
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.paths = {k:Path(cfg[k]) for k in ('app','venv')}
        for key in ('state','home','app','venv','python','node','npm_cli'):
            if not Path(cfg[key]).is_absolute():
                raise ValueError('Fixed absolute owner paths required')
        if any(p.parent.resolve() != self.home.resolve() for p in self.paths.values()) or self.paths['app']==self.paths['venv']:
            raise ValueError('Code and environment must be distinct direct children of game installation')
        if self.root.resolve().is_relative_to(self.home.resolve()):
            raise ValueError('Provider state must be outside agent/game installation')
        if cfg.get('channel') not in ('stable','latest-passing-development') or not cfg.get('required_checks'):
            raise ValueError('Explicit channel and exact required check names are mandatory')

    def gh(self, endpoint):
        return json.loads(run(['gh','api','--hostname','github.com','repos/'+REPOSITORY+'/'+endpoint]))

    def status(self):
        source = read(self.home/'app-source.json')
        revision = source.get('revision')
        if not re.fullmatch('[0-9a-f]{40}', revision or ''):
            raise ContinuityError('Installed exact source revision is missing')
        if self.paths['app'].is_symlink():
            stage=self.paths['app'].resolve().parent
            if stage.parent==self.root/'stages':
                manifest=read(stage/'manifest.json')
                if manifest['revision']!=revision or self.paths['venv'].resolve()!=stage/'venv':
                    raise ContinuityError('Installed source/environment binding changed')
                if any(fingerprint(stage/k)!=manifest['fingerprints'][k] for k in self.paths):
                    raise ContinuityError('Installed source/dependency bytes changed')
        return {'version':revision}

    def candidate(self):
        if self.c['channel']=='stable':
            release = self.gh('releases/latest')
            if release.get('draft') or release.get('prerelease'):
                raise ContinuityError('Stable channel requires a published stable release')
            ref = release['tag_name']
        else:
            ref = 'main'
        if not re.fullmatch('[A-Za-z0-9._-]+', ref):
            raise ValueError('Invalid release reference')
        revision = self.gh('commits/'+ref)['sha']
        if not re.fullmatch('[0-9a-f]{40}', revision):
            raise ValueError('Exact commit required')
        checks = self.gh('commits/'+revision+'/check-runs?per_page=100')
        if checks.get('total_count',0)>100:
            raise ContinuityError('Check list truncated; do not infer green')
        by_name = {}
        for check in checks.get('check_runs',[]):
            if check.get('head_sha') != revision:
                raise ContinuityError('Check source mismatch')
            if check['id'] > by_name.get(check['name'],{}).get('id',-1):
                by_name[check['name']] = check
        for name in self.c['required_checks']:
            check = by_name.get(name,{})
            if check.get('status')!='completed' or check.get('conclusion')!='success':
                raise ContinuityError('Exact source has not passed enrolled checks')
        return revision, {k:{'id':by_name[k]['id'],'conclusion':'success'} for k in self.c['required_checks']}

    def build(self, revision, previous, stage):
        cache = self.root/'source.git'
        if not cache.exists():
            run(['git','clone','--bare','https://github.com/'+REPOSITORY+'.git',str(cache)],stderr=subprocess.DEVNULL)
        run(['git','-C',str(cache),'fetch','origin',revision],stderr=subprocess.DEVNULL)
        if subprocess.run(['git','-C',str(cache),'merge-base','--is-ancestor',previous,revision],capture_output=True).returncode:
            raise ContinuityError('Automatic downgrade or unrelated history is not allowed')
        app, venv = stage/'app', stage/'venv'
        app.mkdir(parents=True)
        archive = run(['git','-C',str(cache),'archive',revision])
        with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
            for item in bundle.getmembers():
                if item.issym() or item.islnk() or not (item.isfile() or item.isdir()):
                    raise ContinuityError('Source archive contains unsupported special entries')
                if Path(item.name).is_absolute() or '..' in Path(item.name).parts:
                    raise ContinuityError('Unsafe archive path')
            bundle.extractall(app,filter='data')
        sdk_pin(app)
        environment = {**os.environ,'PATH':str(Path(self.c['node']).parent)+os.pathsep+os.environ.get('PATH',''),
                       'PYTHONDONTWRITEBYTECODE':'1'}
        if int(run([self.c['node'],'--version'],text=True).strip().lstrip('v').split('.')[0])<22:
            raise ContinuityError('Node 22 or newer required')
        run([self.c['node'],self.c['npm_cli'],'ci','--ignore-scripts','--no-audit','--no-fund'],cwd=app,env=environment,stderr=subprocess.STDOUT)
        run([self.c['node'],self.c['npm_cli'],'run','build:screenshots'],cwd=app,env=environment,stderr=subprocess.STDOUT)
        run([self.c['python'],'-m','venv',str(venv)],stderr=subprocess.STDOUT)
        run([str(venv/'bin/python'),'-m','pip','install','--disable-pip-version-check','-r',str(app/'requirements.txt')],env=environment,stderr=subprocess.STDOUT)
        sdk = verify_sdk(venv,app)
        run([str(venv/'bin/python'),'-m','pip','check'],env=environment,stderr=subprocess.STDOUT)
        # Import the real official SDK in its staged environment; no endpoint,
        # home, session or model is created by this packaging test.
        run([str(venv/'bin/python'),'-c','from acp import connect_to_agent; import acp_client'],cwd=app,env=environment,stderr=subprocess.STDOUT)
        run([self.c['node'],'--check','body.cjs'],cwd=app,env=environment,stderr=subprocess.STDOUT)
        if any(not (app/name).is_file() for name in ('update-admission.cjs','update_admission.py','tests/test_installation_guard.py')):
            raise ContinuityError('Candidate cannot preserve installation admission support')
        run([str(venv/'bin/python'),'-m','unittest','discover','-s','tests','-p','test_installation_guard.py'],cwd=app,env=environment,stderr=subprocess.STDOUT)
        run([self.c['node'],'--test','tests/body-lease.test.cjs'],cwd=app,env=environment,stderr=subprocess.STDOUT)
        return sdk

    def plan(self):
        previous = self.status()['version']
        revision, checks = self.candidate()
        if revision == previous:
            return {'available':False,'version':previous}
        stage = self.root/'stages'/str(uuid.uuid4())
        sdk = self.build(revision,previous,stage)
        manifest = {'revision':revision,'checks':checks,'sdk':sdk,
                    'fingerprints':{k:fingerprint(stage/k) for k in self.paths},
                    'python_sha256':hashlib.sha256(Path(self.c['python']).read_bytes()).hexdigest()}
        durable_write(stage/'manifest.json',manifest)
        return {'available':True,'version':revision,'previous':previous,'stage':str(stage),
                'manifest_hash':digest(manifest),'config_hash':digest(self.c),
                'before':{k:fingerprint(p) for k,p in self.paths.items()},
                'source_marker':read(self.home/'app-source.json')}

    def frozen(self, envelope, *, candidate=True):
        if envelope.get('component') != 'minecraft' or str(uuid.UUID(envelope['id'])) != envelope['id']:
            raise ValueError('Wrong source provider envelope')
        plan = envelope['plan']
        stage = Path(plan['stage'])
        if stage.parent != self.root/'stages' or str(uuid.UUID(stage.name)) != stage.name or plan['config_hash'] != digest(self.c):
            raise ContinuityError('Source enrollment/stage changed')
        manifest = read(stage/'manifest.json')
        if digest(manifest) != plan['manifest_hash'] or manifest['revision'] != plan['version']:
            raise ContinuityError('Frozen source manifest changed')
        if candidate:
            for key in self.paths:
                if fingerprint(stage/key) != manifest['fingerprints'][key]:
                    raise ContinuityError('Staged source/dependency bytes changed')
            if hashlib.sha256(Path(self.c['python']).read_bytes()).hexdigest() != manifest['python_sha256']:
                raise ContinuityError('Staged interpreter dependency changed')
            verify_sdk(stage/'venv',stage/'app')
        return plan,stage,self.root/'provider-receipts'/(envelope['id']+'.json')

    def require_prepared(self, transaction, *, rollback=False):
        if str(uuid.UUID(transaction)) != transaction:
            raise ValueError('Current lifecycle transaction required')
        receipt = read(self.root/'transactions'/(transaction+'.json'))
        gate = read(self.home/'installation-updates/gate.json')
        phases=('ready','verifying_body','verified') if rollback else ('ready',)
        if receipt.get('config_hash')!=digest(self.c) or receipt.get('phase') not in phases or not receipt.get('game') or gate != {'version':1,'transaction_id':transaction,'closed':True}:
            raise ContinuityError('Source update requires this transaction settled game boundary')
        from installation_participant import LocalInstallation
        backend=LocalInstallation(self.c);services = backend.services()
        if rollback and receipt['phase'] in ('verifying_body','verified'):
            from installation_guard import continuity, require_idle
            if services['controller']['ActiveState'] not in ('inactive','failed'):
                raise ContinuityError('Never roll back after listener restoration')
            if services['body']['ActiveState']=='active':
                after=backend.capture();require_idle(after)
                continuity(receipt['baseline'],after,body_restart=True)
                # The participant owns this lifecycle action; source exchange
                # never swaps files under a running game process.
                durable_write(self.root/'transactions'/(transaction+'.json'),{**receipt,'phase':'verifying_body'})
                backend.action('body','stop')
                end=time.monotonic()+8
                while backend.services()['body']['ActiveState'] not in ('inactive','failed'):
                    if time.monotonic()>=end:raise ContinuityError('Rollback body did not settle')
                    time.sleep(.1)
            durable_write(self.root/'transactions'/(transaction+'.json'),{**receipt,'phase':'ready'})
            services=backend.services()
        if any(v['ActiveState'] not in ('inactive','failed') or str(v['MainPID'])!='0' for v in services.values()):
            raise ContinuityError('Source exchange requires both owned units stopped')

    def apply(self, envelope, transaction):
        plan,stage,path = self.frozen(envelope)
        self.require_prepared(transaction)
        if path.exists():
            if read(path)['state']=='applied':return self.verify(envelope)
            raise ContinuityError('Uncertain source cutover requires code rollback, never replay')
        if read(self.home/'app-source.json') != plan['source_marker'] or any(fingerprint(p)!=plan['before'][k] for k,p in self.paths.items()):
            raise ContinuityError('Installed source changed after planning')
        backup = self.root/'backups'/envelope['id'];backup.mkdir(parents=True)
        if any(p.parent.stat().st_dev != backup.stat().st_dev for p in self.paths.values()):
            raise ContinuityError('Atomic source exchange requires same filesystem')
        durable_write(path,{'state':'applying','transaction_id':transaction})
        for key,target in self.paths.items():
            os.rename(target,backup/key)
            sync_directories(target.parent,backup)
            target.symlink_to(stage/key, target_is_directory=True)
            sync_directories(target.parent)
        durable_write(self.home/'app-source.json',{**plan['source_marker'],'revision':plan['version'],
                                                 'python':str(self.paths['venv']/'bin/python')})
        durable_write(path,{'state':'applied','transaction_id':transaction})
        return self.verify(envelope)

    def rollback(self,envelope,transaction):
        plan,stage,path = self.frozen(envelope,candidate=False)
        self.require_prepared(transaction,rollback=True)
        if not path.exists():
            if read(self.home/'app-source.json')!=plan['source_marker'] or any(fingerprint(p)!=plan['before'][k] for k,p in self.paths.items()):
                raise ContinuityError('No cutover receipt and installed source changed')
            durable_write(path,{'state':'rolled_back','transaction_id':transaction,'untouched':True})
            return self.verify(envelope)
        backup = self.root/'backups'/envelope['id']
        durable_write(path,{'state':'rolling_back','transaction_id':transaction})
        for key,target in self.paths.items():
            old = backup/key
            if os.path.lexists(old):
                if os.path.lexists(target):
                    if not target.is_symlink() or os.readlink(target)!=str(stage/key):
                        raise ContinuityError('Unknown installed source; preserve for recovery')
                    target.unlink()
                os.rename(old,target)
                sync_directories(target.parent,backup)
            if fingerprint(target)!=plan['before'][key]:
                raise ContinuityError('Previous code/environment does not match')
        durable_write(self.home/'app-source.json',plan['source_marker'])
        durable_write(path,{'state':'rolled_back','transaction_id':transaction})
        return self.verify(envelope)

    def verify(self,envelope):
        plan,stage,path = self.frozen(envelope,candidate=False)
        state = read(path)['state'] if path.exists() else None
        if state not in ('applied','rolled_back'):
            raise ContinuityError('Source exchange has not settled')
        if state=='applied':
            self.frozen(envelope)
            for key,target in self.paths.items():
                if not target.is_symlink() or os.readlink(target)!=str(stage/key):
                    raise ContinuityError('Installed source pointer mismatch')
            expected={**plan['source_marker'],'revision':plan['version'],'python':str(self.paths['venv']/'bin/python')}
            if read(self.home/'app-source.json')!=expected:
                raise ContinuityError('Installed source revision mismatch')
        elif any(fingerprint(p)!=plan['before'][k] for k,p in self.paths.items()) or read(self.home/'app-source.json')!=plan['source_marker']:
            raise ContinuityError('Source rollback verification failed')
        return {'verified':True,'version':plan['version'] if state=='applied' else plan['previous']}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True)
    parser.add_argument('action',choices=('status','plan','apply','rollback','verify'));args=parser.parse_args()
    os.umask(0o077);provider=Provider(read(args.config))
    with installation_lock(provider.root/'installation.lock'):
        if args.action in ('status','plan'):result=getattr(provider,args.action)()
        else:
            envelope=read(os.environ['CONSTELLATION_UPDATE_PLAN'])
            if args.action=='verify':result=provider.verify(envelope)
            else:result=getattr(provider,args.action)(envelope,os.environ['CONSTELLATION_UPDATE_TRANSACTION'])
    print(json.dumps(result))


if __name__=='__main__':main()
