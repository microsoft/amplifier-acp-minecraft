"""Minecraft fixed native profiles and no-start registration.

The shared installer supplies an already protected owner configuration/root.
This module does not manufacture ACLs, grant platform access, create an engine
session, enable a disabled service, or start a game connection.
"""
from pathlib import Path
import hashlib
import json
import os
import re
from installation_guard import ContinuityError, read, service_stopped
from installation_session_probe import saved_endpoint


def profiles(cfg, owner_config, bundle, services):
    home,state=Path(cfg['home']),Path(cfg['state'])
    owner_config,bundle=Path(owner_config),Path(bundle)
    if (any(not p.is_absolute() for p in (home,state,owner_config,bundle))
            or home==state or set(services)!={'body','controller'}):
        raise ValueError('Explicit private native installation paths and services required')
    manifest=read(bundle/'manifest.json')
    native=manifest.get('native_platform',{})
    if native.get('repository')!='microsoft/amplifier-constellation':
        raise ValueError('Package lacks the shared installation driver')
    commands=manifest['commands']
    def command(name):
        rel=commands[name];path=Path(rel)
        if path.is_absolute() or '..' in path.parts or '\\' in rel or ':' in rel:
            raise ValueError('Package command escaped its root')
        result=bundle/path
        if not result.is_file() or not result.resolve().is_relative_to(bundle.resolve()):
            raise ValueError('Package command unavailable or outside package')
        entry=manifest['files'][rel]
        if result.is_symlink():
            if entry.get('link')!=os.readlink(result):raise ValueError('Package command link changed')
            entry=manifest['files'][result.resolve().relative_to(bundle.resolve()).as_posix()]
        if entry.get('sha256')!=hashlib.sha256(result.read_bytes()).hexdigest():
            raise ValueError('Package command differs from manifest')
        return result
    driver,python,node=command('native_driver'),command('python'),command('node')
    if native['driver_sha256']!=hashlib.sha256(driver.read_bytes()).hexdigest():
        raise ValueError('Shared driver provenance differs')
    if cfg['native_platform']['driver']!=str(driver) or cfg['native_platform']['python']!=str(python):
        raise ValueError('Domain native runtime paths differ from package')
    driver_config=Path(cfg['native_platform']['config'])
    if not driver_config.is_absolute():raise ValueError('Fixed protected driver config required')
    endpoint,_,_=saved_endpoint(home)  # validates an existing binding, never creates one
    if not isinstance(endpoint.get('command'),list) or not endpoint['command']:
        raise ValueError('Original engine endpoint is missing')
    if not Path(endpoint['command'][0]).is_absolute() or not Path(endpoint.get('cwd','')).is_absolute():
        raise ValueError('Native engine profile needs its existing absolute executable/cwd')
    app=home/'app';entry=app/'native_entry.py'
    if not entry.is_file():raise ValueError('Stage the exact verified package application before registration')
    registration={};applications={}
    for kind,service in services.items():
        if (service.get('manager') not in ('systemd_user','launch_agent','scheduled_task')
                or not re.fullmatch(r'[A-Za-z0-9_.-]{1,180}',service.get('name',''))):
            raise ValueError('Fixed owner service descriptor required')
        registration[kind]={'executable':str(driver),'args':['--config',str(driver_config),'service-run','--service',kind],
            'cwd':str(home),'description':'Minecraft '+kind,'autostart':False}
        argv=([str(app/'body.cjs'),str(home/'config.json')] if kind=='body' else
              ['-I',str(entry),'controller','--home',str(home),'--native-owner-config',str(owner_config)])
        applications[kind]={'executable':str(node if kind=='body' else python),'args':argv,'cwd':str(home),
                            'identity_path':str(state/(kind+'-identity.json'))}
    return {'version':1,'roots':{'home':str(home),'state':str(state)},
        'locks':{'installation':str(state/'installation.lock')},'services':services,
        'registrations':registration,'service_applications':applications,
        'commands':{
          'session_endpoint':{'executable':endpoint['command'][0],'args':endpoint['command'][1:],
                              'cwd':endpoint['cwd'],'timeout_seconds':200},
          'session_probe':{'executable':str(python),'args':['-I',str(entry),'connection-probe',
              '--home',str(home),'--result','{result}','--native-owner-config',str(owner_config)],
              'cwd':str(home),'timeout_seconds':200,'result_root':'state'}},
        'exchanges':{key:{'lock':'installation','profile':{'current':str(home/key),'roots':{'state':str(state)}}}
                     for key in ('app','venv')}}


def register_no_start(session, expected_config, observed_config):
    if observed_config!=expected_config:
        raise ContinuityError('Installed protected native profile differs from reviewed setup')
    required={'service.register','service.snapshot','process.identity'}
    if not required.issubset(session.describe().get('operations',[])):
        raise ContinuityError('Shared driver does not advertise fresh setup support')
    result={}
    with session.lock('installation'):
        for key in ('body','controller'):
            creation=session.service_register(key)
            state=session.service_snapshot(key)
            if creation.get('created') is True and not service_stopped(state):
                raise ContinuityError('Fresh native setup did not remain stopped')
            result[key]={'creation':creation,'state':state}
    return {'registered':True,'start_requested':False,'services':result,
            'session_created':False,'prompt_sent':False,'context_registration_changed':False}
