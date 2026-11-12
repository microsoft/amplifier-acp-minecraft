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
import urllib.request
from pathlib import Path

from installation_guard import ContinuityError, digest, durable_write, installation_lock, read, enrollment_ids, service_active, service_stopped
from installation_retention import Retention

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
    metadata += list(venv.glob('Lib/site-packages/agent_client_protocol-*.dist-info/direct_url.json'))
    if len(metadata) != 1:
        raise ContinuityError('One official SDK installation required')
    direct = read(metadata[0]);vcs = direct.get('vcs_info',{})
    if direct.get('url') != SDK_URL or vcs.get('commit_id') != commit or vcs.get('vcs') != 'git' or direct.get('dir_info',{}).get('editable'):
        raise ContinuityError('SDK immutable upstream provenance mismatch')
    return {'commit':commit, 'direct_url':direct}


class Provider:
    def __init__(self, cfg, backend=None):
        enrollment_ids(cfg)
        self.backend = backend
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
        self.retention = Retention(cfg)

    def gh(self, endpoint):
        route='repos/'+REPOSITORY+'/'+endpoint
        request=urllib.request.Request('https://api.github.com/'+route,headers={'User-Agent':'Minecraft-installation-updates'})
        try:
            with urllib.request.urlopen(request,timeout=15) as response:
                return json.loads(response.read(2*1024*1024))
        except urllib.error.HTTPError as error:
            # Public metadata needs no credentials. Optional owner gh auth is
            # only a fallback for API rate limiting, never agent credentials.
            if error.code not in (403,429):raise
            return json.loads(run(['gh','api','--hostname','github.com',route]))

    def status(self):
        source = read(self.home/'app-source.json')
        revision = source.get('revision')
        if not re.fullmatch('[0-9a-f]{40}', revision or ''):
            raise ContinuityError('Installed exact source revision is missing')
        if self.paths['app'].is_symlink() or (self.c.get('native_platform') and getattr(self.paths['app'],'is_junction',lambda:False)()):
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
        if self.c.get('native_platform'):
            from installation_native_package import stage_package
            return stage_package(self,revision,previous,stage)
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
        self.screenshot_browser(app, prepare=True)
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

    def screenshot_policy(self):
        config = read(self.home/'config.json') if (self.home/'config.json').exists() else {}
        policy = config.get('screenshots') or {}
        if policy.get('enabled') is not True:
            return {'enabled':False}
        browser = policy.get('browser_path')
        if browser is not None and (not isinstance(browser,str) or not Path(browser).is_absolute()):
            raise ContinuityError('Screenshot browser override must be an absolute owner path')
        return {'enabled':True,'browser_path':browser}

    def screenshot_browser(self, app, *, prepare=False):
        policy = self.screenshot_policy()
        if not policy['enabled']:
            return
        command = [self.c['node'],str(app/'screenshot-browser.cjs'),'prepare' if prepare else 'check']
        if policy['browser_path']:
            command += ['--browser-path',policy['browser_path']]
        run(command,cwd=app,stderr=subprocess.STDOUT)

    def build_inputs(self):
        return {'config_hash':digest(self.c),'screenshot_browser':self.screenshot_policy(), **{
            key+'_sha256':hashlib.sha256(Path(self.c[key]).read_bytes()).hexdigest()
            for key in ('python','node','npm_cli')}}

    def reusable(self, revision, inputs):
        for identifier in self.retention.stage_ids():
            record = self.retention.owned('stage', identifier)
            if record.get('state') != 'ready' or record.get('revision') != revision:
                continue
            stage = self.retention.safe_path('stage', identifier)
            try:
                manifest = read(stage/'manifest.json')
                if (set(p.name for p in stage.iterdir()) != ({'app','venv','manifest.json','package','package-receipt.json'} if self.c.get('native_platform') else {'app','venv','manifest.json'})
                        or manifest.get('build_inputs') != inputs
                        or digest(manifest) != record.get('manifest_hash')
                        or any(fingerprint(stage/k) != manifest['fingerprints'][k] for k in self.paths)):
                    continue
                verify_sdk(stage/'venv', stage/'app')
                self.screenshot_browser(stage/'app', prepare=True)
            except (OSError, ValueError, KeyError, ContinuityError):
                continue
            # Do not rewrite an immutable manifest referenced by a saved plan.
            # A lost plan-output acknowledgment can safely offer the same bytes.
            self.retention.mark('stage', identifier, last_offered=time.time())
            return stage, manifest
        return None

    def cleanup(self, *, failed=None):
        result = self.retention.prune(fingerprint, failed=failed)
        durable_write(self.root/'cleanup-last.json', result)
        return result

    def plan(self):
        if not self.c.get('shared_plans'):
            raise ContinuityError('Enroll shared_plans before automatic source checks')
        previous = self.status()['version']
        revision, checks = self.candidate()
        if revision == previous:
            return {'available':False,'version':previous,'cleanup':self.cleanup()}
        before = {k:fingerprint(p) for k,p in self.paths.items()}
        inputs = self.build_inputs()
        cached = self.reusable(revision, inputs)
        cleanup = self.cleanup()
        if cleanup.get('held') and not cached:
            raise ContinuityError('Retention references are uncertain; refusing another source build')
        if cached:
            stage, manifest = cached
        else:
            stage = self.root/'stages'/str(uuid.uuid4())
            self.retention.safe_path('stage', stage.name)
            self.retention.mark('stage', stage.name, state='building', created_at=time.time(), revision=revision)
            try:
                sdk = self.build(revision,previous,stage)
                manifest = {'revision':revision,'checks':checks,'sdk':sdk,'build_inputs':inputs,
                            'fingerprints':{k:fingerprint(stage/k) for k in self.paths},
                            'python_sha256':inputs['python_sha256']}
                durable_write(stage/'manifest.json',manifest)
                self.retention.mark('stage', stage.name, state='ready', last_offered=time.time(),
                                    manifest_hash=digest(manifest))
            except Exception as error:
                self.retention.mark('stage', stage.name, state='failed', error_type=type(error).__name__)
                self.cleanup(failed=stage.name)
                raise
        return {'available':True,'version':revision,'previous':previous,'stage':str(stage),
                'manifest_hash':digest(manifest),'config_hash':digest(self.c),
                'before':before,'cleanup':cleanup,
                'source_marker':read(self.home/'app-source.json'),'source_marker_version':2}

    def frozen(self, envelope, *, candidate=True):
        if envelope.get('component') != enrollment_ids(self.c)[1]['minecraft'] or str(uuid.UUID(envelope['id'])) != envelope['id']:
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
            if 'screenshot_browser' in manifest.get('build_inputs',{}):
                if manifest['build_inputs']['screenshot_browser'] != self.screenshot_policy():
                    raise ContinuityError('Screenshot browser policy changed after staging')
                self.screenshot_browser(stage/'app')
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
        backend=self.backend if self.backend is not None else LocalInstallation(self.c)
        services = backend.services()
        if rollback and receipt['phase'] in ('verifying_body','verified'):
            from installation_guard import continuity, require_idle
            if not service_stopped(services['controller']):
                raise ContinuityError('Never roll back after listener restoration')
            if service_active(services['body']):
                after=backend.capture();require_idle(after)
                continuity(receipt['baseline'],after,body_restart=True)
                # The participant owns this lifecycle action; source exchange
                # never swaps files under a running game process.
                durable_write(self.root/'transactions'/(transaction+'.json'),{**receipt,'phase':'verifying_body'})
                backend.action('body','stop')
                end=time.monotonic()+8
                while not service_stopped(backend.services()['body']):
                    if time.monotonic()>=end:raise ContinuityError('Rollback body did not settle')
                    time.sleep(.1)
            durable_write(self.root/'transactions'/(transaction+'.json'),{**receipt,'phase':'ready'})
            services=backend.services()
        if any(not service_stopped(v) for v in services.values()):
            raise ContinuityError('Source exchange requires both owned units stopped')

    def installed_marker(self, plan, stage):
        relative=(self.c.get('native_platform') or {}).get('environment_python','bin/python')
        if relative not in ('bin/python','bin/python3','python.exe','Scripts/python.exe'):
            raise ContinuityError('Unrecognized private environment interpreter path')
        marker={**plan['source_marker'],'revision':plan['version'],
                'python':str(self.paths['venv']/relative)}
        # Old retained plans preserve their original verification/rollback
        # contract. New plans replace the stale copied inventory with actual
        # frozen installed application bytes, including built UI assets.
        if plan.get('source_marker_version') == 2:
            app=stage/'app'
            marker['files']={str(p.relative_to(app)):hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(app.rglob('*')) if p.is_file() and not p.is_symlink()
                and not {'node_modules','__pycache__'}.intersection(p.relative_to(app).parts)
                and p.suffix != '.pyc'}
            marker['files_scope']='installed_app_excluding_node_modules_and_python_caches'
        return marker

    def native_exchange(self,envelope,transaction,stage):
        from installation_native_exchange import NativeExchange
        if not self.backend or not hasattr(self.backend,'native'):
            raise ContinuityError('Explicit native source backend is required')
        targets={key:{'root':'state','path':(stage/key).relative_to(self.root).as_posix()} for key in self.paths}
        return NativeExchange(self.c,self.backend.native,self.backend,transaction,envelope['id'],targets)

    def native_source(self,action,envelope,transaction):
        plan,stage,path=self.frozen(envelope,candidate=action=='apply')
        self.require_prepared(transaction,rollback=action=='rollback')
        exchange=self.native_exchange(envelope,transaction,stage)
        marker=read(self.home/'app-source.json')
        if path.exists():
            receipt=read(path)
            if receipt['transaction_id']!=transaction:raise ContinuityError('Source transaction changed')
            if receipt['state']==('applied' if action=='apply' else 'rolled_back'):
                return self.verify(envelope)
        else:
            if marker!=plan['source_marker'] or any(fingerprint(p)!=plan['before'][k] for k,p in self.paths.items()):
                raise ContinuityError('Original native source changed after planning')
            if action=='rollback':
                durable_write(path,{'state':'rolled_back','transaction_id':transaction,'untouched':True})
                return self.verify(envelope)
        if action=='apply':
            if marker not in (plan['source_marker'],self.installed_marker(plan,stage)):
                raise ContinuityError('Native source marker changed independently')
            durable_write(path,{'state':'applying','transaction_id':transaction})
            exchange.apply()
            durable_write(self.home/'app-source.json',self.installed_marker(plan,stage))
            durable_write(path,{'state':'applied','transaction_id':transaction})
        else:
            durable_write(path,{'state':'rolling_back','transaction_id':transaction})
            if exchange.value is None:
                if any(fingerprint(p)!=plan['before'][k] for k,p in self.paths.items()):
                    raise ContinuityError('Missing native exchange evidence with changed source')
            else:exchange.rollback()
            if any(fingerprint(p)!=plan['before'][k] for k,p in self.paths.items()):
                raise ContinuityError('Previous native source differs after rollback')
            durable_write(self.home/'app-source.json',plan['source_marker'])
            durable_write(path,{'state':'rolled_back','transaction_id':transaction})
        return self.verify(envelope)

    def apply(self, envelope, transaction):
        if self.c.get('native_platform'):
            return self.native_source('apply',envelope,transaction)
        plan,stage,path = self.frozen(envelope)
        self.require_prepared(transaction)
        if path.exists():
            if read(path)['state']=='applied':return self.verify(envelope)
            raise ContinuityError('Uncertain source cutover requires code rollback, never replay')
        if read(self.home/'app-source.json') != plan['source_marker'] or any(fingerprint(p)!=plan['before'][k] for k,p in self.paths.items()):
            raise ContinuityError('Installed source changed after planning')
        backup = self.root/'backups'/envelope['id']
        self.retention.safe_path('backup', envelope['id'])
        self.retention.mark('backup', envelope['id'], state='retained', created_at=time.time(),
                            transaction_id=transaction)
        backup.mkdir(parents=True)
        if any(p.parent.stat().st_dev != backup.stat().st_dev for p in self.paths.values()):
            raise ContinuityError('Atomic source exchange requires same filesystem')
        durable_write(path,{'state':'applying','transaction_id':transaction})
        for key,target in self.paths.items():
            os.rename(target,backup/key)
            sync_directories(target.parent,backup)
            target.symlink_to(stage/key, target_is_directory=True)
            sync_directories(target.parent)
        durable_write(self.home/'app-source.json',self.installed_marker(plan,stage))
        durable_write(path,{'state':'applied','transaction_id':transaction})
        return self.verify(envelope)

    def rollback(self,envelope,transaction):
        if self.c.get('native_platform'):
            return self.native_source('rollback',envelope,transaction)
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
            if self.c.get('native_platform'):
                self.native_exchange(envelope,read(path)['transaction_id'],stage).verify('applied')
            for key,target in ({} if self.c.get('native_platform') else self.paths).items():
                if not target.is_symlink() or os.readlink(target)!=str(stage/key):
                    raise ContinuityError('Installed source pointer mismatch')
            expected=self.installed_marker(plan,stage)
            if read(self.home/'app-source.json')!=expected:
                raise ContinuityError('Installed source revision mismatch')
        elif any(fingerprint(p)!=plan['before'][k] for k,p in self.paths.items()) or read(self.home/'app-source.json')!=plan['source_marker']:
            raise ContinuityError('Source rollback verification failed')
        return {'verified':True,'version':plan['version'] if state=='applied' else plan['previous']}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True)
    parser.add_argument('action',choices=('status','plan','apply','rollback','verify'));args=parser.parse_args()
    from contextlib import ExitStack
    os.umask(0o077);cfg=read(args.config)
    with ExitStack() as scope:
        backend=None
        if cfg.get('native_platform'):
            from installation_native import native_scope, NativeInstallation
            backend=NativeInstallation(cfg,scope.enter_context(native_scope(cfg)))
        provider=Provider(cfg,backend=backend)
        scope.enter_context(installation_lock(provider.root/'installation.lock'))
        if args.action in ('status','plan'):result=getattr(provider,args.action)()
        else:
            envelope=read(os.environ['CONSTELLATION_UPDATE_PLAN'])
            if args.action=='verify':result=provider.verify(envelope)
            else:result=getattr(provider,args.action)(envelope,os.environ['CONSTELLATION_UPDATE_TRANSACTION'])
    print(json.dumps(result))


if __name__=='__main__':main()
