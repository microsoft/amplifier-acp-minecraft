#!/usr/bin/env python3
"""Emit an owner-reviewed updater registration delta; no enrollment or starts."""
import argparse
import json
import sys
import platform
from pathlib import Path
from installation_guard import read, enrollment_ids
from installation_participant import verification_seconds
from installation_source_provider import Provider


def registration(config, helper_directory, python):
    if platform.system()!='Linux':
        raise ValueError('This lifecycle driver requires Linux systemd-user; do not enroll on other platforms')
    config, helper_directory, python = map(Path,(config,helper_directory,python))
    if not all(p.is_absolute() for p in (config,helper_directory,python)):
        raise ValueError('Use absolute owner-installed helper/config/interpreter paths')
    cfg=read(config);Provider(cfg);verification_seconds(cfg)
    participant_id, ids = enrollment_ids(cfg)
    plans=Path(cfg.get('shared_plans',''))
    if (not plans.is_absolute() or plans.resolve()!=plans or not plans.is_dir()
            or plans.is_relative_to(Path(cfg['home'])) or plans.is_relative_to(Path(cfg['state']))):
        raise ValueError('Enroll the actual independent shared plans directory for source retention')
    if any(p.resolve().is_relative_to(Path(cfg['home']).resolve()) for p in (config,helper_directory)):
        raise ValueError('Updater code/config must be outside mutable game source and agent mounts')
    helper=Path(cfg['task_helper'])
    if not helper.is_absolute() or helper.is_symlink() or not helper.is_file():
        raise ValueError('Enroll the existing separate pure task-helper executable')
    if helper.parent != Path(cfg['home'])/'task-helpers':
        raise ValueError('Task helper must use the dedicated game helper directory')
    for filename in ('installation_participant.py','installation_source_provider.py','installation_session_probe.py','installation_retention.py','connection_state.py'):
        if not (helper_directory/filename).is_file():raise ValueError('Install fixed owner helper files first')
    scope={'services':[],'instance':False,'slack_homes':[]}
    def command(script,action):return [str(python),str(helper_directory/script),'--config',str(config),action]
    result = {'components':[
        {'id':ids['minecraft'],'provider':'command','protocol':2,'restart_scope':dict(scope),
         'commands':{action:command('installation_source_provider.py',action) for action in ('status','plan','apply','rollback','verify')}},
        {'id':ids['task-helpers'],'kind':'runtime','binary':str(helper),'restart_scope':dict(scope)}],
        'participants':[{'id':participant_id,'protocol':1,
                         'components':[ids['minecraft'],ids['task-helpers'],'instance','runtime','engine','container-image'],
                         'commands':{action:command('installation_participant.py',action) for action in ('prepare','verify','restore')}}]}
    if cfg.get('service_connection') is not None:
        from installation_connection import descriptor
        entry = descriptor(cfg)
        for filename in ('installation_connection.py','connection_state.py','connection_session_job.py'):
            if not (helper_directory/filename).is_file():
                raise ValueError('Install fixed connection helpers before enrollment')
        result['service_connections'] = {'schema':1,
            'services':[{'id':'minecraft','label':'Minecraft'}],
            'connections':[{**entry,'service':'minecraft','commands':{
                action:command('installation_connection.py',action)
                for action in ('status','connect','disconnect')}}]}
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True)
    parser.add_argument('--helpers',required=True);parser.add_argument('--python',default=sys.executable)
    args=parser.parse_args();print(json.dumps(registration(args.config,args.helpers,args.python),indent=2))
