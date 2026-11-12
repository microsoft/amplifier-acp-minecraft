#!/usr/bin/env python3
"""Save an owner-prepared, unused Minecraft connection. No starts or Instance writes.

Server choices are fixed installation slots, not browser-supplied destinations.
Provisioning/routes remain the domain setup prerequisite. Status resumes only
the same file-only save operation after a lost reply.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

from installation_connection import Backend, descriptor, stored_continuity, PROVIDER_FIELDS
from installation_guard import (ContinuityError, NotIdle, digest, durable_write,
                                installation_lock, read, require_idle)
from installation_source_provider import verify_sdk


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def exact_file(path, expected):
    path = Path(path)
    if not path.is_absolute() or path.is_symlink() or not path.is_file() or file_hash(path) != expected:
        raise ContinuityError('Prepared connection or route evidence changed')
    return path


def load(path):
    path = Path(path)
    c = read(path)
    if set(c) != {'schema', 'state', 'agent_home', 'helpers', 'python', 'slots'} or c['schema'] != 1:
        raise ValueError('Unsupported owner setup template')
    for key in ('state', 'agent_home', 'helpers', 'python'):
        if not Path(c[key]).is_absolute():
            raise ValueError('Fixed absolute owner paths required')
    agent = Path(c['agent_home']).resolve()
    if any(p.resolve().is_relative_to(agent) for p in
           (path, *(Path(c[k]) for k in ('state','helpers','python')))):
        raise ValueError('Fixed setup control files must remain outside agent mounts')
    if not isinstance(c['slots'], list) or not 1 <= len(c['slots']) <= 16:
        raise ValueError('Enroll bounded prepared server choices')
    ids, homes, states, providers = set(), set(), set(), set()
    for slot in c['slots']:
        if (set(slot)-{'activate_context_on_first_connect'} != {'id', 'label', 'config', 'config_sha256', 'route_receipt', 'route_sha256'}
                or type(slot.get('activate_context_on_first_connect',False)) is not bool
                or not re.fullmatch(r'[a-z][a-z0-9-]{0,40}', slot['id']) or slot['id'] in ids
                or not isinstance(slot['label'], str) or not 1 <= len(slot['label'].strip()) <= 120):
            raise ValueError('Invalid or duplicate prepared server choice')
        cfg = read(exact_file(slot['config'], slot['config_sha256']))
        route = read(exact_file(slot['route_receipt'], slot['route_sha256']))
        home, state = Path(cfg['home']), Path(cfg['state'])
        if not home.is_absolute() or not state.is_absolute() or state.resolve().is_relative_to(home.resolve()):
            raise ValueError('Connection owner state must be outside its home')
        if state.resolve() == Path(c['state']).resolve():
            raise ValueError('Add and connection locks need separate owner state directories')
        if any(p.resolve().is_relative_to(agent) or p.resolve().is_relative_to(home.resolve())
               for p in (path, state, Path(slot['config']), Path(slot['route_receipt']))):
            raise ValueError('Prepared connection control files must remain owner-private')
        if any(Path(c[k]).resolve().is_relative_to(home.resolve()) for k in ('state', 'helpers', 'python')):
            raise ValueError('Fixed setup helpers/state must be outside game homes')
        provider = route.get('context', {}).get('provider_id')
        if str(home.resolve()) in homes or str(state.resolve()) in states or provider in providers:
            raise ValueError('Prepared slots must have independent homes, state and context')
        ids.add(slot['id']); homes.add(str(home.resolve())); states.add(str(state.resolve())); providers.add(provider)
    c['revision'] = file_hash(path)
    return c


def enrollment(c, path):
    args = [c['python'], str(Path(__file__).resolve()), '--config', str(Path(path).resolve())]
    return {'id':'minecraft', 'label':'Minecraft', 'add':{'revision':c['revision'], 'fields':[
        {'name':'label', 'label':'Connection name', 'kind':'text', 'required':True, 'max_length':120},
        {'name':'server', 'label':'Prepared server', 'kind':'choice', 'required':True,
         'choices':[{'value':s['id'], 'label':s['label']} for s in c['slots']]}]},
        'add_commands':{action:args+[action] for action in ('add','status')}}


class Prerequisites:
    def __init__(self, c, cfg, backend=None):
        self.c, self.cfg = c, cfg
        self.game = backend if backend is not None else Backend(cfg)

    def providers(self):
        agent = Path(self.c['agent_home'])
        result = subprocess.run([str(agent/'bin/agent-instance'), '--home', str(agent),
            'api', 'GET', 'context/providers'], capture_output=True, text=True, timeout=5, check=True)
        return json.loads(result.stdout)['providers']

    def check(self, route):
        home = Path(self.cfg['home'])
        cfg = read(home/'config.json')
        if (route.get('schema') != 1 or route.get('home') != str(home)
                or route.get('config_sha256') != file_hash(home/'config.json')
                or route.get('endpoint_sha256') != file_hash(home/'endpoint.json')
                or not isinstance(route.get('checked_at'), str) or not route['checked_at']):
            raise ContinuityError('Private route preparation is missing or changed')
        game, context = route.get('game', {}), route.get('context', {})
        if (game != {'host':cfg['host'], 'port':cfg['port'], 'verified':True}
                or context.get('runtime_namespace_verified') is not True
                or context.get('provider_id') != cfg.get('context_provider_id')
                or context.get('url') != 'http://127.0.0.1:'+str(cfg['control_port'])
                or not context.get('secret_ref') or not route.get('configuration_files')):
            raise ContinuityError('Approved private game and own-context routes are required')
        for path, expected in route['configuration_files'].items():
            exact_file(path, expected)
        matched = [p for p in self.providers() if p.get('id') == context['provider_id']]
        if (len(matched) != 1 or matched[0].get('url') != context['url']
                or matched[0].get('secret_ref') != context['secret_ref'] or matched[0].get('enabled') is not False):
            raise ContinuityError('Prepared context must match and remain explicitly disabled until mapped offline')
        if cfg.get('incoming_chat_only') is not True or cfg.get('human_task_intake', {}).get('enabled') is True:
            raise ContinuityError('A fresh saved connection must have no task-intake opt-in')
        verify_sdk(Path(self.cfg['venv']), Path(self.cfg['app']))
        for name in ('installation_connection.py', 'connection_state.py', 'connection_session_job.py',
                     'installation_session_probe.py', 'installation_participant.py', 'installation_guard.py',
                     'installation_source_provider.py', 'installation_retention.py', 'update_admission.py'):
            if not (Path(self.c['helpers'])/name).is_file():
                raise ContinuityError('Install the complete reviewed owner helper set first')
        snapshot = self.game.capture()
        snapshot['prepared_provider'] = {k:matched[0].get(k) for k in PROVIDER_FIELDS}
        snapshot['prepared_provider_configured'] = matched[0].get('configured') is True
        require_idle(snapshot)
        history = read(home/'workshop.json')
        if (history.get('task') is not None or history.get('turn') is not None or history.get('action_sequences')
                or (home/'session.json').exists() or (Path(self.cfg['state'])/'active.json').exists()):
            raise ContinuityError('Only a prepared unused connection can be added; preserve used homes')
        for s in snapshot['services'].values():
            if s['ActiveState'] != 'inactive' or str(s['MainPID']) != '0' or s['UnitFileState'] != 'disabled' or s['LoadState'] != 'loaded':
                raise NotIdle('Prepared game services must remain inactive and disabled')
        return snapshot


def write_once(path, value):
    path = Path(path)
    if path.is_symlink():
        raise ContinuityError('Setup output must not be a symbolic link')
    if path.exists():
        if read(path) != value:
            raise ContinuityError('Saved setup output conflicts; never overwrite another installation')
    else:
        durable_write(path, value)


def operation(c, request, backend=None):
    if (set(request) != {'schema','service_id','revision','action','request_id','values'}
            or request['schema'] != 1 or request['service_id'] != 'minecraft'
            or request['revision'] != c['revision'] or request['action'] not in ('add','status')):
        raise ValueError('Unsupported or stale setup request')
    rid = request['request_id']
    if not isinstance(rid,str) or str(uuid.UUID(rid)) != rid:
        raise ValueError('Canonical setup request ID required')
    values = request['values']
    if (not isinstance(values,dict) or set(values) != {'label','server'}
            or not isinstance(values['server'],str)
            or not isinstance(values['label'],str) or not 1 <= len(values['label'].strip()) <= 120
            or any(ord(ch) < 32 for ch in values['label'])):
        raise ValueError('Only a bounded connection label and enrolled server choice are accepted')
    slot = next((s for s in c['slots'] if s['id'] == values['server']), None)
    if slot is None:
        raise ValueError('Server choice is not authorized by this installation')
    root = Path(c['state']); path = root/'operations'/(rid+'.json')
    identity = {'request_id':rid, 'revision':c['revision'], 'values':values}
    response = {'schema':1,'service_id':'minecraft','request_id':rid,'state':'unknown',
                'settled':False,'message':'Setup has not been confirmed.'}
    journal = read(path) if path.exists() else None
    if journal:
        if journal['identity'] != identity:
            raise ContinuityError('Setup request ID reused with changed values')
        if journal.get('result'):
            return journal['result']
    else:
        if request['action'] == 'status':
            return response
        journal = {'identity':identity, 'phase':'accepted'}
        durable_write(path,journal)
    cfg = read(exact_file(slot['config'],slot['config_sha256']))
    route = read(exact_file(slot['route_receipt'],slot['route_sha256']))
    home, state = Path(cfg['home']), Path(cfg['state'])
    backend = backend or Prerequisites(c,cfg)
    claim = root/'slots'/(slot['id']+'.json')
    if journal['phase'] == 'accepted':
        try:
            if claim.exists() and read(claim) != identity:
                raise ContinuityError('This prepared slot was already saved by another request')
            if any((home/p).exists() for p in ('installation-updates/gate.json','installation-connections/state.json')):
                raise ContinuityError('Prepared slot already has lifecycle state')
            baseline = backend.check(route)
            connection = {'id':'minecraft-'+slot['id'], 'label':values['label'],
                'revision':digest({'template':c['revision'],'identity':identity}),
                'context_provider_ids':[route['context']['provider_id']]}
            saved_cfg = {**cfg,'service_connection':connection,
                'prepared_context':{'agent_home':c['agent_home'],'provider':{
                    'id':route['context']['provider_id'],'url':route['context']['url'],
                    'secret_ref':route['context']['secret_ref']}}}; descriptor(saved_cfg)
            if slot.get('activate_context_on_first_connect') is True:
                expected = baseline.get('prepared_provider')
                if (not isinstance(expected,dict) or set(expected)!=set(PROVIDER_FIELDS)
                        or baseline.get('prepared_provider_configured') is not True
                        or expected['enabled'] is not False
                        or any(not isinstance(expected[k],str) or not expected[k]
                               for k in PROVIDER_FIELDS if k!='enabled')):
                    raise ContinuityError('One-use activation needs the exact initially disabled provider')
                saved_cfg['prepared_context']['activation'] = {'version':1,'add_request_id':rid,
                    'template_revision':c['revision'],'slot_id':slot['id'],'expected_provider':expected}
            saved_path = state/'saved-connection-config.json'
            if saved_path.exists():
                raise ContinuityError('Saved connection configuration already exists')
            journal.update(phase='saving', baseline=baseline, config=saved_cfg, config_path=str(saved_path))
            durable_write(path,journal)
        except NotIdle:
            response.update(state='busy',message='Waiting for the prepared connection to settle; nothing has been saved or started.')
            return response
        except (ContinuityError,FileNotFoundError):
            response.update(state='failed',settled=True,message='This choice is not an unused, stopped connection with verified private game/context routes and current registration. Complete owner setup first; existing connections were preserved.')
            journal['result']=response;durable_write(path,journal)
            return response
    # File-only idempotent completion. Never start services, register context,
    # create a session, enable tasks or write the shared host registration.
    write_once(claim,identity)
    stored_continuity(journal['baseline'],backend.check(route))
    saved_cfg = journal['config']; entry = descriptor(saved_cfg)
    initial = {'action':'setup','revision':entry['revision'],'config_hash':digest(saved_cfg),
        'phase':'terminal','baseline':journal['baseline'],
        'result':{'schema':1,'connection_id':entry['id'],'request_id':rid,'state':'disconnected',
                  'settled':True,'message':'Prepared connection saved offline; no service has been started.'}}
    write_once(journal['config_path'],saved_cfg)
    write_once(state/'connections'/(rid+'.json'),initial)
    write_once(home/'installation-updates/gate.json',{'version':1,'transaction_id':rid,'closed':True})
    write_once(home/'installation-connections/state.json',{'schema':1,'phase':'disconnected','request_id':rid})
    args = [c['python'],str(Path(c['helpers'])/'installation_connection.py'),'--config',journal['config_path']]
    response.update(state='saved',settled=True,message=(
        'Saved offline. Connect will finish the authorized one-time provider activation when supported; no work was authorized.'
        if saved_cfg['prepared_context'].get('activation') else
        'Saved offline. Owner setup must confirm the mapped context gate is closed and enable this prepared provider before Connect. No work was authorized.'),
        connection={**entry,'service':'minecraft','commands':{a:args+[a] for a in ('status','connect','disconnect')}})
    journal.update(phase='saved',result=response);durable_write(path,journal)
    return response


def main():
    os.umask(0o077)
    parser=argparse.ArgumentParser();parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('action',choices=('enrollment','add','status'));args=parser.parse_args()
    c=load(args.config)
    if args.action=='enrollment':
        print(json.dumps(enrollment(c,args.config)));return
    data=sys.stdin.buffer.read(65537)
    if len(data)>65536:raise ValueError('Setup request too large')
    request=json.loads(data)
    if request.get('action')!=args.action:raise ValueError('Fixed command action mismatch')
    with installation_lock(Path(c['state'])/'installation.lock'):
        slot=next((s for s in c['slots'] if s['id']==request.get('values',{}).get('server')),None)
        if slot is None:raise ValueError('Unapproved server')
        cfg=read(slot['config'])
        with installation_lock(Path(cfg['state'])/'installation.lock'):
            print(json.dumps(operation(c,request)))


if __name__=='__main__':main()
