"""Fixed local fresh-home setup. No start, account login, session or enrollment.

Only a newly created private root is admitted. A partial/unknown setup is kept
for inspection; invoking setup again never retries registrations or writes.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import subprocess
import uuid

from installation_guard import ContinuityError, owner_io, service_stopped
from installation_native import NativeIO
from installation_native_package import copy_private_payload, fill_created_payload_file, target
from installation_native_setup import profiles
from native_package import validate


def encoded(value):
    return json.dumps(value,sort_keys=True).encode('utf-8')


def plan_paths(bundle,plan):
    if type(plan.get('schema')) is not int or plan['schema']!=1:
        raise ValueError('Fresh setup plan schema 1 required')
    if set(plan)-{'schema','root','game','endpoint','service_connection'}:
        raise ValueError('Unknown setup plan field')
    root=Path(plan['root'])
    if (not root.is_absolute() or root.resolve()!=root or root==bundle
            or root.is_relative_to(bundle) or bundle.is_relative_to(root)):
        raise ValueError('Fresh absolute installation root must be separate from package')
    if root.exists() or root.is_symlink():
        raise ContinuityError('Setup never reuses an existing root, including a partial attempt')
    if not root.parent.is_dir():raise ValueError('Setup parent must already exist')
    if sys.platform not in ('linux','darwin','win32'):raise ValueError('Unsupported native service platform')
    game=plan['game'];endpoint=plan['endpoint']
    if (not isinstance(game,dict) or not isinstance(game.get('token'),str) or not game['token']
            or type(game.get('control_port')) is not int or not 1<=game['control_port']<=65535):
        raise ValueError('Explicit body control port and token required')
    if (not isinstance(endpoint,dict) or not isinstance(endpoint.get('command'),list)
            or not endpoint['command'] or not all(isinstance(x,str) for x in endpoint['command'])
            or not Path(endpoint['command'][0]).is_absolute()
            or not Path(endpoint.get('cwd','')).is_absolute()):
        raise ValueError('Explicit existing engine executable and working directory required')
    if 'task_helpers' in game:raise ValueError('Fresh setup supplies its own fixed packaged task-helper path')
    if not Path(endpoint['command'][0]).is_file() or not Path(endpoint['cwd']).is_dir():
        raise ValueError('Existing engine endpoint must be available; setup does not install or sign it in')
    return root,root/'home',root/'state'


def setup(bundle,plan):
    from constellation_native import Session, NativeSession, initialize_root, initialize_config
    bundle=Path(bundle).resolve();root,home,state=plan_paths(bundle,plan)
    manifest=validate(bundle)
    if manifest.get('target')!=target() or manifest.get('source_clean') is not True:
        raise ValueError('Exact clean native target package required')
    native=manifest.get('native_platform',{})
    if native.get('abi')!=1 or not native.get('library_sha256'):
        raise ValueError('Packaged caller-process library/driver pair required')
    if any(manifest.get('commands',{}).get(k) not in manifest['files'] for k in ('native_driver','native_library')):
        raise ValueError('Native commands must be inventoried package files')
    driver=bundle/manifest['commands']['native_driver'];library=bundle/manifest['commands']['native_library']
    if (library.is_symlink() or driver.is_symlink()
            or hashlib.sha256(library.read_bytes()).hexdigest()!=native['library_sha256']
            or hashlib.sha256(driver.read_bytes()).hexdigest()!=native['driver_sha256']):
        raise ValueError('Package native pair provenance differs')
    identifier=str(uuid.uuid4());intent={'schema':1,'id':identifier,'phase':'staging',
        'plan_sha256':hashlib.sha256(encoded(plan)).hexdigest(),
        'manifest_sha256':hashlib.sha256((bundle/'manifest.json').read_bytes()).hexdigest(),
        'source':manifest['source_commit'],'services':{},'start_requested':False,
        'session_created':False,'prompt_sent':False,'enrolled':False}
    # created:false is not unused-slot proof. There is no recovery-by-rerun.
    for directory in (root,home,state):
        if initialize_root(driver,directory).get('created') is not True:
            raise ContinuityError('Fresh setup ownership was not acquired')
    bootstrap=state/'setup-native.json';config=state/'native.json';owner=state/'owner.json'
    base={'version':1,'roots':{'home':str(home),'state':str(state)},
          'locks':{'installation':str(state/'installation.lock')}}
    initialize_config(driver,bootstrap,base)
    # Initial setup has exclusive allocation of a new, unpublished home, not a
    # helper-held installation lease. Use the fixed CLI only to allocate private
    # empty files. Close it before copying, and never reuse a partial setup root.
    # All subsequent lock-dependent work uses the actual caller-process ABI.
    packaged_driver,packaged_library=driver,library
    copies=[(packaged_driver,state/'native'/driver.name,native['driver_sha256']),
            (packaged_library,state/'native'/library.name,native['library_sha256'])]
    with Session(packaged_driver,bootstrap) as initial:
        initial.private_write('state','setup.json',encoded(intent),create_only=True)
        initial.private_dir('state','native')
        for _,destination,_ in copies:
            initial.private_write('state',destination.relative_to(state).as_posix(),b'',create_only=True)
    for source,destination,digest in copies:
        with source.open('rb') as stream:fill_created_payload_file(destination,stream,0o700)
        if hashlib.sha256(destination.read_bytes()).hexdigest()!=digest:
            raise ContinuityError('Private native copy differs from verified package')
    driver,library=copies[0][1],copies[1][1]
    python=bundle/manifest['commands']['python'];node=bundle/manifest['commands']['node']
    relative_python=Path(manifest['commands']['python']).relative_to('python')
    helper_name=Path(manifest['commands']['task_helper']).name
    cfg={'home':str(home),'state':str(state),'app':str(home/'app'),'venv':str(home/'venv'),
         'python':str(python),'node':str(node),'npm_cli':str(bundle/'app/package.json'),
         'task_helper':str(home/'task-helpers'/helper_name),'channel':'stable',
         'required_checks':['published-native-package'],'session_verification_seconds':12,
         'native_platform':{'version':1,'driver':str(driver),'config':str(config),
           'library':str(library),'library_sha256':native['library_sha256'],
           'python':str(home/'venv'/relative_python),'environment_python':relative_python.as_posix(),
           'services':{'body':'body','controller':'controller'},'regenerable_tree_removal':1,'data_journals':1}}
    if 'service_connection' in plan:cfg['service_connection']=plan['service_connection']
    names={role:'minecraft-'+identifier+'-'+role for role in ('body','controller')}
    services={}
    for role,name in names.items():
        if sys.platform=='linux':
            name+='.service';manager='systemd_user';definition=Path.home()/'.config/systemd/user'/name
        elif sys.platform=='darwin':
            manager='launch_agent';definition=Path.home()/'Library/LaunchAgents'/(name+'.plist')
        elif sys.platform=='win32':manager='scheduled_task';definition=None
        else:raise ValueError('Unsupported native service platform')
        services[role]={'manager':manager,'name':name,'definition_path':str(definition) if definition else None}
    # Bootstrap and final config use the identical installation lock. The first
    # scope ends before opening the final profile; saved intent spans this gap.
    with NativeSession(library,driver,bootstrap) as session,session.lock('installation'):
        io=NativeIO(cfg,session)
        with owner_io(io):
            io.write(state/'setup.json',intent)
            # Missing parents are not absent journals. Create fixed parents at
            # fresh setup, never as a repair during admission or observation.
            io.prepare_data_journal_directories()
            for directory in ('stages','backups'):io.mkdir(state/directory)
            for prefix,destination in [('app',home/'app'),('python',home/'venv'),('task-helper',home/'task-helpers')]:
                copy_private_payload(bundle,prefix,destination,manifest)
            game=json.loads(json.dumps(plan['game']))
            game['task_helpers']={'command':[cfg['task_helper']]}
            if (game.get('screenshots') or {}).get('enabled') is True and not game['screenshots'].get('browser_path'):
                browser=subprocess.check_output([str(node),'-e',
                    "process.stdout.write(require('playwright').chromium.executablePath())"],
                    cwd=bundle/'app',env={**os.environ,'PLAYWRIGHT_BROWSERS_PATH':str(bundle/'browsers')},
                    text=True,timeout=15)
                path=Path(browser)
                if not path.is_file() or not path.resolve().is_relative_to(bundle/'browsers'):
                    raise ContinuityError('Packaged screenshot browser unavailable')
                if path.relative_to(bundle).as_posix() not in manifest['files']:
                    raise ContinuityError('Screenshot browser is not inventoried')
                game['screenshots']['browser_path']=str(path)
            io.write(home/'config.json',game);io.write(home/'endpoint.json',plan['endpoint'])
            io.write(home/'app-source.json',{'revision':manifest['source_commit'],'package':intent['manifest_sha256']})
            fixed=profiles(cfg,owner,bundle,services)
            initialize_config(driver,config,fixed)
            io.write(owner,cfg)
            intent['phase']='registration_pending';io.write(state/'setup.json',intent)
    with NativeSession(library,driver,config) as session,session.lock('installation'):
        io=NativeIO(cfg,session)
        if json.loads((state/'setup.json').read_bytes())!=intent:
            raise ContinuityError('Setup intent changed before registration')
        for role in ('body','controller'):
            intent['services'][role]={'phase':'dispatch_pending','profile':services[role]}
            io.write(state/'setup.json',intent)
            created=session.service_register(role)
            observed=session.service_snapshot(role)
            if created.get('created') is not True or not service_stopped(observed):
                raise ContinuityError('Fresh service name was not new and stopped; retain setup intent')
            intent['services'][role]={'phase':'registered_stopped','profile':services[role],
                                      'creation':created,'snapshot':observed}
            io.write(state/'setup.json',intent)
        intent['phase']='registered_stopped';io.write(state/'setup.json',intent)
    return {'id':identifier,'phase':intent['phase'],'owner_config':str(owner),
            'receipt':str(state/'setup.json'),'start_requested':False,'enrolled':False,
            'session_created':False,'prompt_sent':False}
