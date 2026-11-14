"""Packaged Linux installations reuse lifecycle v1 as their own service user."""
import copy
import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from installation_participant import LocalInstallation, Participant, main
from test_installation_participant import FakeInstallation


class SystemParticipantTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root/'game'
        self.home.mkdir()
        self.cfg = {'home':str(self.home), 'state':str(self.root/'owner-state'),
                    'units':{'body':'anchor-minecraft-body.service',
                             'controller':'anchor-minecraft-controller.service'},
                    'system_manager':{'version':1, 'uid':999, 'gid':990, 'actions':'sudo'}}
        self.envelope = {'id':str(uuid.uuid4()), 'participant':'minecraft', 'plan':{
            'schema':1, 'transaction_id':str(uuid.uuid4()), 'operation':'apply',
            'components':['instance']}}

    def owner(self):
        return patch.multiple('installation_participant.os',
                              geteuid=lambda:999, getegid=lambda:990)

    def test_wrong_owner_refuses_before_state_or_gate_write_even_with_backend(self):
        backend = FakeInstallation(self.home)
        for uid, gid in ((0,0), (999,0), (1000,990)):
            with self.subTest(uid=uid, gid=gid), patch.multiple(
                    'installation_participant.os', geteuid=lambda:uid, getegid=lambda:gid):
                with self.assertRaisesRegex(ValueError, 'service user'):
                    Participant(self.cfg, self.envelope, backend)
            self.assertFalse(Path(self.cfg['state']).exists())
            self.assertFalse((self.home/'installation-updates').exists())
        self.assertEqual(backend.actions, [])

    def test_cli_owner_check_precedes_lock_directory_creation(self):
        config, plan = self.root/'config.json', self.root/'plan.json'
        config.write_text(json.dumps(self.cfg)); plan.write_text(json.dumps(self.envelope))
        with patch('sys.argv', ['participant','--config',str(config),'prepare']), \
                patch.dict(os.environ, CONSTELLATION_UPDATE_PLAN=str(plan),
                           CONSTELLATION_UPDATE_OUTCOME='unchanged'), \
                patch.multiple('installation_participant.os', geteuid=lambda:0, getegid=lambda:0), \
                patch('installation_participant.os.umask'), \
                patch('installation_participant.installation_lock') as lock:
            with self.assertRaisesRegex(ValueError, 'service user'):
                main()
        lock.assert_not_called()
        self.assertFalse(Path(self.cfg['state']).exists())

    def test_readonly_system_commands_never_use_sudo_but_actions_are_exact(self):
        fragment = self.root/'unit.service'; fragment.write_text('[Service]\n')
        def reply(argv, **kwargs):
            if 'show' in argv:
                return ('ActiveState=inactive\nMainPID=0\nLoadState=loaded\n'
                        'UnitFileState=enabled\nFragmentPath='+str(fragment)+'\n')
            return '[Service]\n'
        with self.owner(), patch('installation_participant.subprocess.check_output', side_effect=reply) as call:
            backend = LocalInstallation(self.cfg)
            self.assertEqual(set(backend.services()), {'body','controller'})
            for kind in ('body','controller'):
                for action in ('start','stop'):
                    backend.action(kind, action)
        commands = [c.args[0] for c in call.call_args_list]
        self.assertEqual(len(commands), 8)
        for command in commands[:4]:
            self.assertEqual(command[:3], ['/bin/systemctl','--system','--no-ask-password'])
            self.assertIn(command[3], ('show','cat'))
        self.assertEqual(commands[4:], [
            ['/usr/bin/sudo','-n','/bin/systemctl','--system','--no-ask-password',
             action,'--no-block',self.cfg['units'][kind]]
            for kind in ('body','controller') for action in ('start','stop')])

    def test_no_arbitrary_units_actions_arguments_or_prefix(self):
        with self.owner(), patch('installation_participant.subprocess.check_output') as call:
            backend = LocalInstallation(self.cfg)
            for kind, action in [('other','start'), ('body','restart'), ('controller','enable')]:
                with self.assertRaises(ValueError): backend.action(kind, action)
            for args in [('daemon-reload',), ('cat','ssh.service'),
                         ('start','--no-block','ssh.service'),
                         ('show',self.cfg['units']['body'],'--all')]:
                with self.assertRaises(ValueError): backend.command(*args)
        call.assert_not_called()
        for change in [None, {'version':1,'uid':0,'gid':990,'actions':'sudo'},
                       {'version':1,'uid':999,'gid':990,'actions':['sudo','sh']},
                       {'version':1,'uid':999,'gid':990,'actions':'sudo','prefix':['sh']}]:
            cfg = {**self.cfg, 'system_manager':change}
            with self.owner(), self.assertRaises(ValueError): LocalInstallation(cfg)
        for units in [{'body':'--all','controller':'valid.service'},
                      {'body':'same.service','controller':'same.service'},
                      {**self.cfg['units'],'extra':'other.service'}]:
            with self.owner(), self.assertRaises(ValueError):
                LocalInstallation({**self.cfg,'units':units})

    def test_direct_system_authorization_and_default_user_mode(self):
        cfg = copy.deepcopy(self.cfg); cfg['system_manager']['actions'] = 'direct'
        with self.owner(), patch('installation_participant.subprocess.check_output') as call:
            LocalInstallation(cfg).action('controller','stop')
        self.assertEqual(call.call_args.args[0], ['/bin/systemctl','--system','--no-ask-password',
            'stop','--no-block','anchor-minecraft-controller.service'])
        cfg.pop('system_manager'); cfg['venv'] = str(self.root/'venv')
        cfg['units'] = {'body':'acp-minecraft-body-fixture.service',
                        'controller':'acp-minecraft-agent-fixture.service'}
        with patch('installation_participant.subprocess.check_output') as call:
            backend = LocalInstallation(cfg); backend.action('body','start')
        self.assertEqual(call.call_args.args[0], ['systemctl','--user','start','--no-block',cfg['units']['body']])
        self.assertEqual(backend.session_python(), self.root/'venv/bin/python')
        self.assertEqual(backend.session_arguments(), [])

    def test_system_mode_cannot_mix_with_native_driver_or_root_identity(self):
        with self.owner(), self.assertRaises(ValueError):
            Participant({**self.cfg,'native_platform':{'version':1}}, self.envelope,
                        FakeInstallation(self.home))
        self.assertFalse(Path(self.cfg['state']).exists())

    def test_instance_update_keeps_original_state_and_lost_restore_is_idempotent(self):
        # Existing core controls admission and receipts; system mode changes only I/O routing.
        from installation_guard import durable_write
        backend = FakeInstallation(self.home)
        before = {name:(self.home/name).read_bytes() for name in ('workshop.json','session.json')}
        with self.owner():
            participant = Participant(self.cfg, self.envelope, backend)
            self.assertFalse(participant.prepare()['ready'])
            durable_write(self.home/'installation-updates/controller-idle.json',{
                'transaction_id':self.envelope['plan']['transaction_id'],
                **backend.units['controller']['process_identity']})
            for _ in range(5):
                if participant.prepare()['ready']: break
            else: self.fail('not ready after settled controller acknowledgment')
            self.assertTrue(participant.verify('applied')['verified'])
            self.assertTrue(participant.restore('applied')['restored'])
            actions = copy.deepcopy(backend.actions)
            self.assertTrue(Participant(self.cfg,self.envelope,backend).restore('applied')['restored'])
        self.assertEqual(backend.actions, actions)
        self.assertEqual(actions,[('controller','stop'),('session','load-only'),('controller','start')])
        self.assertFalse((self.home/'installation-updates/gate.json').exists())
        for name, content in before.items(): self.assertEqual((self.home/name).read_bytes(),content)


if __name__ == '__main__': unittest.main()
