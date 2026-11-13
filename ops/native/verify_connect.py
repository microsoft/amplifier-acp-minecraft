"""Packaged composition (adapted from qualified harness SHA256 8869ebe386e4288dc80d2b3e0e5b8e7f8b1c1accc8b55290f6d9c7dd6b26dc65): real NativeSession/probe/SDK; synthetic body and services.

This does not enroll Minecraft or exercise OS service controls. Every connection
action is a separate short Python process. The native endpoint wrapper and
durable probe are the production paths from the frozen Minecraft source.
"""
import argparse
import copy
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from unittest import mock


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def load_modules(spec):
    sys.path[:0] = [spec['facade'], spec['source'], str(Path(spec['test_source'])/'tests')]


def backend_from_fixture(cfg, session, fixture):
    from installation_native import connection_backend
    from test_installation_connection import Fake
    native = connection_backend(cfg, session)
    fake = Fake.__new__(Fake)
    fake.home = Path(cfg['home'])
    fake.units, fake.body, fake.actions = fixture['units'], fixture['body'], fixture['actions']
    # Only non-probe body/service observations and controls are synthetic.
    # The real NativeConnection owns start_probe and probe_alive unchanged.
    for name in ('capture', 'services', 'action', 'connected'):
        setattr(native, name, getattr(fake, name))
    return native


def child(spec_path):
    spec = json.loads(spec_path.read_text())
    load_modules(spec)
    from constellation_native import Unknown
    from installation_native import native_scope
    from installation_guard import installation_lock
    from installation_connection import Connection
    cfg = json.loads(Path(spec['owner_config']).read_text())
    root = Path(spec['root'])
    fixture = json.loads((root/'synthetic-service-state.json').read_text())
    envelope = spec['envelope']
    if spec.get('capture') == 'worker':
        assert json.loads(sys.stdin.buffer.read(65537)) == envelope
    observed = {'pid': os.getpid(), 'calls': [], 'call_timings': [], 'lock_acquired': False,
                'child_started_monotonic':time.monotonic()}
    caught = None
    with native_scope(cfg) as session, installation_lock(Path(cfg['state'])/'installation.lock'):
        observed['lock_acquired'] = True
        observed['caller_identity'] = session.process_identity(os.getpid())
        backend = backend_from_fixture(cfg, session, fixture)
        library = session._library
        invoke = library.invoke
        def intercepted(function, *args):
            request = json.loads(args[1]) if function is library.request else None
            if request:
                observed['calls'].append(request['op'])
                if request['op'] == 'process.launch':
                    journal = json.loads((Path(cfg['state'])/'connections'/f"{envelope['request_id']}.json").read_text())
                    assert journal['phase'] == 'verifying' and 'probe_process' not in journal
                    observed['intent_before_dispatch'] = journal
                    if spec['mode'] != 'launch':
                        raise AssertionError('STATUS attempted a second probe launch')
            started=time.monotonic()
            raw = invoke(function, *args)
            if request:observed['call_timings'].append({'op':request['op'],'seconds':time.monotonic()-started})
            if request and request['op'] == 'process.launch':
                # Retain the real native identity only in the test observer;
                # the domain does not receive it when reply loss is injected.
                observed['actual_launch_response'] = json.loads(raw)
                write(root/'launch-observation.json', observed['actual_launch_response'])
                if spec['lose_ack']:
                    return b'{"version":1,"id":"lost-launch-reply","outcome":"ok","result":{}}'
            return raw
        with mock.patch.object(library, 'invoke', side_effect=intercepted):
            try:
                observed['result'] = Connection(cfg, envelope, backend).run()
            except Unknown as error:
                caught = error
                observed['unknown'] = {'type': type(error).__name__, 'code': error.code}
                if spec['mode'] != 'launch' or not spec['lose_ack']:
                    raise
    # All domain writes happen before exiting the native critical section.
    # This extra file persists only synthetic service observations for the test.
    write(root/'synthetic-service-state.json', fixture)
    observed['lock_scope_exited'] = True
    observed['child_finished_monotonic']=time.monotonic()
    write(spec['child_receipt'], observed)
    assert bool(caught) == (spec['mode'] == 'launch' and spec['lose_ack'])
    if spec.get('capture') == 'worker':
        if caught is not None:
            raise caught  # Actual Worker retains failed command as unknown; no synthetic success.
        print(json.dumps(observed['result']))


def wait_for(predicate, seconds, description):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        if predicate():
            return
        time.sleep(.02)
    raise AssertionError(description)


def run_case(spec, destination, lose_ack, worker=None):
    from constellation_native import NativeSession, initialize_root, initialize_config
    from installation_native import native_scope
    from installation_guard import installation_lock, durable_write, read
    from installation_connection import Connection
    from test_installation_connection import Fake
    # Only fresh fixture roots use the shared test preparation helper. Native
    # initialize_root still validates rather than repairing production parents.
    sys.path.insert(0,str(Path(spec['shared'])/'tests/native_python'))
    from test_driver import protect
    temporary = Path(tempfile.mkdtemp(prefix='connect-abi-', dir=destination)).resolve()
    protect(temporary)
    root = temporary/'installation'
    driver_input, library = Path(spec['driver']), Path(spec['library'])
    report = {'lost_launch_ack': lose_ack, 'invocations': [], 'production_operations': False}
    cfg = None
    identity = None
    endpoint_identity = None
    launch_invoked = False
    cleaned = False
    pending_output=[]
    callers=[]
    try:
        initialize_root(driver_input, root)
        home, state = root/'home', root/'state'
        for path in (home, state):
            initialize_root(driver_input, path)
        driver = root/driver_input.name
        shutil.copyfile(driver_input, driver)
        driver.chmod(0o700)
        owner_config = state/'owner.json'
        config = state/'driver.json'
        cfg = {'home': str(home), 'state': str(state), 'session_verification_seconds': 12,
               'native_platform': {'version': 1,'data_journals':1, 'driver': str(driver), 'config': str(config),
                  'library': str(library), 'library_sha256': sha(library),
                  'python': sys.executable, 'services': {'body':'body','controller':'controller'}},
               'service_connection': {'id':'minecraft-probe-fixture','label':'Disposable probe',
                  'revision':'a'*64,'context_provider_ids':['minecraft:probe-fixture']}}
        source = Path(spec['source'])
        (home/'app').mkdir(mode=0o700)
        for name in ('acp_client.py','prompt_lifecycle.py'):
            shutil.copyfile(source/name, home/'app'/name)
        endpoint_wrapper = root/'endpoint.py'
        endpoint_wrapper.write_text(
            'import json, os, runpy, sys, time\nfrom pathlib import Path\n'
            + 'root=Path('+repr(str(root))+')\n'
            + 'sys.path.insert(0,'+repr(spec['facade'])+')\n'
            + 'from constellation_native import NativeSession\n'
            + 'with NativeSession('+repr(str(library))+','+repr(str(driver))+','+repr(str(config))+') as session:\n'
            + ' identity=session.process_identity(os.getpid())\n'
            + '(root/"endpoint-started.json").write_text(json.dumps(identity))\n'
            + 'until=time.monotonic()+20\n'
            + 'while not (root/"release-endpoint").exists():\n'
            + ' if time.monotonic()>until: raise TimeoutError("bounded disposable endpoint wait")\n'
            + ' time.sleep(.02)\n'
            + 'runpy.run_path('+repr(str(Path(spec['test_source'])/'tests/session_probe_fixture.py'))+',run_name="__main__")\n', encoding='utf-8')
        endpoint = {'command':[sys.executable,'-I',str(endpoint_wrapper)], 'cwd':str(root),
                    'env':{'PROBE_LOG':str(root/'acp.jsonl')}}
        game_config = {'control_port':1234,'token':'disposable-unused-no-http'}
        effective = {**endpoint,'mcp_servers':[{'type':'http','name':'minecraft','url':'http://127.0.0.1:1234/mcp',
                    'headers':[{'name':'Authorization','value':'Bearer '+game_config['token']}]}]}
        probe_wrapper = root/'probe.py'
        probe_wrapper.write_text('import sys,runpy\nsys.path[:0]='+repr([spec['facade'],spec['source']])
            +'\nrunpy.run_module("connection_session_job",run_name="__main__")\n',encoding='utf-8')
        manager = {'linux':'systemd_user','darwin':'launch_agent','win32':'scheduled_task'}[sys.platform]
        services = {k:{'manager':manager,'name':'minecraft-unused-probe-fixture-'+k+('.service' if sys.platform=='linux' else ''),
                       'definition_path':None} for k in ('body','controller')}
        # Shared test-only owner+DACL preparation for synthetic fixture files.
        sys.path.insert(0,str(Path(spec['shared'])/'tests/native_python'))
        from test_driver import protect
        for item in [root,*root.rglob('*')]:
            if not item.is_symlink():protect(item)
        if os.name!='nt':driver.chmod(0o700)
        initialize_config(driver, config, {'version':1,'roots':{'home':str(home),'state':str(state)},
            'locks':{'installation':str(state/'installation.lock')},'services':services,
            'commands':{
                'session_endpoint':{'executable':endpoint['command'][0],'args':endpoint['command'][1:],
                    'cwd':str(root),'timeout_seconds':60},
                'session_probe':{'executable':sys.executable,'args':['-I',str(probe_wrapper),'--home',str(home),
                    '--result','{result}','--native-owner-config',str(owner_config)],
                    'cwd':str(root),'timeout_seconds':60,'result_root':'state'}}})
        # All fixture setup then goes through production domain/native I/O.
        with native_scope(cfg) as session, installation_lock(state/'installation.lock'):
            from installation_native import NativeIO
            NativeIO(cfg,session).prepare_data_journal_directories()
            fake = Fake(home)
            durable_write(home/'config.json', game_config)
            durable_write(home/'endpoint.json', endpoint)
            durable_write(home/'session.json',{'session':'original-fixture-session',
                'binding':hashlib.sha256(json.dumps(effective,sort_keys=True).encode()).hexdigest()})
            durable_write(owner_config,cfg)
            disconnect_id, request_id = str(uuid.uuid4()), str(uuid.uuid4())
            def connection(identifier, action='status'):
                return Connection(cfg,{'schema':1,'connection_id':cfg['service_connection']['id'],
                    'revision':'a'*64,'request_id':identifier,'action':action},fake)
            connection(disconnect_id,'disconnect').run()
            durable_write(home/'installation-updates/controller-idle.json',
                {'transaction_id':disconnect_id,**fake.units['controller']['process_identity']})
            for _ in range(8):
                disconnected = connection(disconnect_id).run()
                if disconnected['settled']:break
            assert disconnected['state']=='disconnected' and disconnected['settled']
            connection(request_id,'connect').run()
            for _ in range(8):
                ready = connection(request_id).run()
                if ready.get('context_ready'):break
            assert ready.get('context_ready') and connection(request_id).value['phase']=='context_ready'
        protected = {p.name:p.read_bytes() for p in home.iterdir() if p.is_file()}
        fixture = {'units':fake.units,'body':fake.body,'actions':fake.actions}
        write(root/'synthetic-service-state.json',fixture)
        base_child = {**spec,'root':str(root),'owner_config':str(owner_config),'lose_ack':lose_ack,
                      'envelope':{'schema':1,'connection_id':cfg['service_connection']['id'],
                                  'revision':'a'*64,'request_id':request_id,'action':'status'}}
        def invoke(mode):
            number=len(report['invocations'])
            child_spec=destination/f'{"lost" if lose_ack else "normal"}-{number}-input.json'
            child_receipt=destination/f'{"lost" if lose_ack else "normal"}-{number}-result.json'
            write(child_spec,{**base_child,'mode':mode,'child_receipt':str(child_receipt)})
            started=time.monotonic()
            if spec.get('capture') == 'worker':
                command=[sys.executable,'-I',str(Path(__file__).resolve()),'--child',str(child_spec)]
                entry={'id':base_child['envelope']['connection_id'],'revision':'a'*64,'commands':{'status':command}}
                record={'mode':mode,'capture':'actual_worker.connection_call'}
                try:
                    result=worker.connection_call(entry,'status',request_id)
                    record['worker_result']=result
                except ValueError as error:
                    record['worker_error']=str(error)
                    assert mode=='launch' and lose_ack and str(error)=='connection_command_failed'
                record['elapsed']=time.monotonic()-started
                record['receipt']=read(child_receipt)
                report['invocations'].append(record)
                if 'worker_error' in record:
                    assert record['receipt']['unknown'] and record['receipt']['lock_scope_exited']
                else:
                    assert all(result[k]==v for k,v in record['receipt']['result'].items())
                return record['receipt']
            process=subprocess.Popen([sys.executable,'-I',str(Path(__file__).resolve()),'--child',str(child_spec)],
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,close_fds=True)
            callers.append(process)
            # Process exit and pipe EOF are different facts on Windows. Retain
            # PIPE capture, but measure exit independently so leaked inherited
            # handles cannot turn an endpoint wait into a caller-lifetime claim.
            code=process.wait(timeout=30)
            record={'mode':mode,'caller_exit_seconds':time.monotonic()-started,'returncode':code}
            try:
                stdout,stderr=process.communicate(timeout=1)
                record.update(stdout=stdout,stderr=stderr,output_pending_after_caller_exit=False)
            except subprocess.TimeoutExpired:
                record.update(stdout='',stderr='',output_pending_after_caller_exit=True)
                pending_output.append((process,record))
            record['elapsed']=time.monotonic()-started
            report['invocations'].append(record)
            assert code==0,record
            record['receipt']=read(child_receipt)
            return record['receipt']
        launch_invoked=True
        first=invoke('launch')
        assert first['lock_scope_exited']
        assert first['calls'].count('process.launch')==1
        identity=first['actual_launch_response']['result']
        journal_path=state/'connections'/f'{request_id}.json'
        journal=read(journal_path)
        assert journal['phase']=='verifying'
        assert ('probe_process' not in journal) if lose_ack else journal['probe_process']==identity
        wait_for(lambda:(root/'endpoint-started.json').exists(),10,'Real supervised endpoint did not start')
        endpoint_identity=read(root/'endpoint-started.json')
        with NativeSession(library,driver,config) as observation:
            assert not observation.process_matches(first['caller_identity'])
            assert observation.process_matches(identity)
            assert observation.process_matches(endpoint_identity)
            report['short_caller_exited_probe_and_endpoint_alive']=True
            report['probe_identity']=identity
            report['endpoint_identity']=endpoint_identity
        before_status=journal_path.read_bytes()
        for _ in range(2):
            status=invoke('status')
            assert status['lock_acquired'] and 'process.launch' not in status['calls']
            assert not status['result']['settled']
            if lose_ack:assert status['result']['state']=='unknown'
            else:
                assert status['result']['context_ready']
                assert 'process.matches' in status['calls']
            assert journal_path.read_bytes()==before_status
            assert not Path(journal['probe_result']).exists()
            assert (home/'installation-updates/gate.json').exists()
        report['fresh_status_reacquires_lock_before_probe_terminal']=True
        (root/'release-endpoint').touch()
        wait_for(lambda:Path(journal['probe_result']).exists(),15,'Original-session receipt did not arrive')
        report['probe_receipt']=read(journal['probe_result'])
        assert report['probe_receipt']['verified'] is True,report['probe_receipt']
        assert report['probe_receipt']['saved_session_loaded'] is True
        assert report['probe_receipt']['new_session_created'] is False
        assert report['probe_receipt']['prompt_sent'] is False
        for _ in range(4):
            status=invoke('status')
            if status['result']['settled']:break
        assert status['result']['state']=='connected' and status['result']['settled']
        terminal=journal_path.read_bytes()
        assert invoke('status')['result']==status['result']
        assert journal_path.read_bytes()==terminal
        assert sum(r['receipt']['calls'].count('process.launch') for r in report['invocations'])==1
        assert {p.name:p.read_bytes() for p in home.iterdir() if p.is_file()}==protected
        report['acp_events']=[json.loads(line) for line in (root/'acp.jsonl').read_text().splitlines()]
        assert report['acp_events']==[{'action':'initialize'},{'action':'load','session':'original-fixture-session'}]
        report['terminal']=read(journal_path)
        report['original_files_unchanged']=True
        report['one_launch_no_redispatch']=True
        with NativeSession(library,driver,config) as observation:
            wait_for(lambda:not observation.process_matches(identity),10,'Owned supervisor did not exit')
            wait_for(lambda:not observation.process_matches(endpoint_identity),10,'Owned endpoint did not exit')
        report['probe_and_endpoint_exited']=True
        report['passed']=True
    finally:
        primary_error=sys.exc_info()[1]
        if primary_error is not None:
            report['failure']={'type':type(primary_error).__name__,'message':str(primary_error)}
        safe_cleanup=not launch_invoked
        try:
            if cfg:
                for journal in (Path(cfg['state'])/'connections').glob('*.json'):
                    saved=read(journal)
                    if saved.get('probe_result') and Path(saved['probe_result']).is_file():
                        report['terminal_probe_result_before_cleanup']=read(Path(saved['probe_result']))
            if root.exists():
                (root/'release-endpoint').touch(exist_ok=True)
            if identity is None and (root/'launch-observation.json').is_file():
                identity=json.loads((root/'launch-observation.json').read_text())['result']
            if endpoint_identity is None and (root/'endpoint-started.json').is_file():
                endpoint_identity=json.loads((root/'endpoint-started.json').read_text())
            if launch_invoked and identity and cfg:
                with NativeSession(cfg['native_platform']['library'],cfg['native_platform']['driver'],cfg['native_platform']['config']) as observation:
                    wait_for(lambda:not observation.process_matches(identity),65,'Owned supervisor cleanup exceeded fixed native command bound')
                    if endpoint_identity is not None:
                        wait_for(lambda:not observation.process_matches(endpoint_identity),10,'Owned endpoint cleanup did not settle')
                        safe_cleanup=True
            unsettled_callers=[process.pid for process in callers if process.poll() is None]
            if unsettled_callers:
                report['unsettled_caller_pids']=unsettled_callers
                safe_cleanup=False
            if safe_cleanup:
                for process,record in pending_output:
                    stdout,stderr=process.communicate(timeout=1)
                    record.update(stdout=stdout,stderr=stderr,output_collected_after_probe_cleanup=True)
                shutil.rmtree(temporary)
        except Exception as error:
            report['cleanup_error']={'type':type(error).__name__,'message':str(error)}
        finally:
            cleaned=not temporary.exists()
            if not cleaned:
                report['cleanup_unknown_retained_path']=str(temporary)
            report['disposable_home_removed']=cleaned
            report['pipe_lifetime_violation']=bool(pending_output)
            report['passed']=bool(report.get('passed') and cleaned and not report.get('cleanup_error') and not pending_output)
            write(destination/('lost-ack.json' if lose_ack else 'normal.json'),report)
    assert report['passed'],report
    return report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--child',type=Path)
    parser.add_argument('--bundle',type=Path)
    parser.add_argument('--source',type=Path)
    parser.add_argument('--shared',type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--instance',type=Path)
    parser.add_argument('--capture',choices=('worker','pipe'),default='worker')
    args=parser.parse_args()
    if args.child:
        child(args.child)
        return
    import constellation_native
    bundle=args.bundle.resolve();manifest=json.loads((bundle/'manifest.json').read_text())
    spec={'source':str(bundle/'app'),'test_source':str(args.source.resolve()),'shared':str(args.shared.resolve()),
          'facade':str(Path(constellation_native.__file__).resolve().parents[1]),
          'driver':str(bundle/manifest['commands']['native_driver']),
          'library':str(bundle/manifest['commands']['native_library'])}
    spec['capture']=args.capture
    worker=None
    worker_pin=None
    if args.capture=='worker':
        if args.instance is None:parser.error('--instance is required for actual Worker capture')
        worker_pin=json.loads((args.shared/'tests/native_python/fixtures/worker_source.json').read_bytes())
        path=args.instance.resolve()/worker_pin['path']
        assert sha(path)==worker_pin['sha256']
        module=importlib.util.spec_from_file_location('qualified_connect_worker',path)
        worker=importlib.util.module_from_spec(module);module.loader.exec_module(worker)
    load_modules(spec)
    args.output.mkdir()  # create-only: never repair an existing evidence directory
    sys.path.insert(0,str(args.shared.resolve()/'tests/native_python'))
    from test_driver import protect
    protect(args.output)
    result={'scope':'Actual packaged native host Connect; synthetic body/services, real ABI/driver/official-SDK original fixture session','target':manifest['target'],'source':manifest['source_commit'],
            'python':sys.version,'python_executable':sys.executable,
            'sdk_direct_url':json.loads(importlib.metadata.distribution('agent-client-protocol').read_text('direct_url.json')),
            'driver_sha256':sha(spec['driver']),'library_sha256':sha(spec['library']),
            'capture':args.capture,'worker_pin':worker_pin,'cases':[]}
    try:
        for lose_ack in (False,True):
            result['cases'].append(run_case(spec,args.output,lose_ack,worker))
        result['passed']=True
    finally:
        write(args.output/'completion.json',result)
    print(json.dumps({'passed':True,'cases':len(result['cases'])}))


if __name__=='__main__':
    main()
