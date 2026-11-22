"""Authority comes from the selected peer's current call, never tool arguments."""
import copy
import unittest
from acp_client import Client, GAME_TOOLS, TOOL_IDENTITY, _Callbacks, wire


class PermissionIdentity(unittest.IsolatedAsyncioTestCase):
    def client(self, *, legacy=False):
        events = []
        c = Client({}, lambda name, **fields: events.append({'event': name, **fields}))
        c.session = 'current-session'
        c.permission_active = lambda: True
        c.info = {'agentInfo': {'name': 'agent-runtime'}, 'agentCapabilities': {}}
        if not legacy:
            c.info['agentCapabilities']['_meta'] = {TOOL_IDENTITY: {'version': 1}}
        c.events = events
        return c

    def call(self, tool='observe', *, legacy=False, arguments=None):
        call = {'sessionUpdate': 'tool_call', 'toolCallId': 'one',
                'title': 'minecraft / ' + tool, 'kind': 'edit', 'status': 'pending',
                'rawInput': {'server': 'minecraft', 'tool': tool, 'arguments': arguments or {}}}
        if not legacy:
            call['_meta'] = {TOOL_IDENTITY: {'version': 1, 'kind': 'mcp', 'server': 'minecraft', 'name': tool}}
        return call

    def announce(self, c, call):
        c._record_tool_call(call)
        c.tool_calls[call['toolCallId']] = copy.deepcopy(call)

    def outcome(self, c, call, *, session='current-session', options=None):
        request = {k: v for k, v in call.items() if k not in ('sessionUpdate', 'status')}
        return wire(c._permission(session, request, options if options is not None else
                                  [{'kind': 'allow_once', 'optionId': 'once'}]))['outcome']['outcome']

    def test_all_current_tools_remain_available_with_engine_identity(self):
        for tool in GAME_TOOLS:
            c = self.client(); call = self.call(tool)
            self.announce(c, call)
            self.assertEqual(self.outcome(c, call), 'selected', tool)

    def test_model_identity_like_arguments_are_ordinary_mcp_data(self):
        c = self.client(); call = self.call(arguments={'server': 'filesystem', 'tool': 'execute',
            '_meta': {TOOL_IDENTITY: {'version': 1, 'kind': 'builtin', 'name': 'workspace_run'}}})
        self.announce(c, call)
        self.assertEqual(self.outcome(c, call), 'selected')

    def test_builtin_spoofs_denied_with_truthful_payload_free_observation(self):
        for legacy in (False, True):
            for name, args in [('workspace_write', {'path':'secret-marker','content':'SECRET'}),
                               ('workspace_run', {'command':'sh','args':['SECRET']})]:
                c = self.client(legacy=legacy); call = self.call(legacy=legacy)
                call.update(title=name.replace('_', ' '), rawInput={**args, 'server':'minecraft','tool':'observe'})
                if not legacy:
                    call['_meta'][TOOL_IDENTITY] = {'version':1,'kind':'builtin','name':name}
                self.announce(c, call)
                self.assertEqual(self.outcome(c, call), 'cancelled')
                self.assertIsNone(c.events[-1]['tool'])
                self.assertNotIn('SECRET', str(c.events))
                self.assertNotEqual(c.events[-1]['event'], 'game_permission_allowed')

    def test_legacy_actual_native_request_kind_other_is_not_authority(self):
        c=self.client(legacy=True); call=self.call(legacy=True); self.announce(c,call)
        call['kind']='other'
        self.assertEqual(self.outcome(c,call),'selected')
        call['title']='workspace run'
        self.assertEqual(self.outcome(c,call),'cancelled')

    def test_negotiated_request_kind_other_is_accepted_and_is_not_authority(self):
        c=self.client(); call=self.call(); self.announce(c,call)
        call['kind']='other'
        self.assertEqual(self.outcome(c,call),'selected')
        self.assertEqual(c.events[-1]['reason'],'verified_game_tool')
        call['title']='workspace run'
        self.assertEqual(self.outcome(c,call),'cancelled')
        c=self.client(); call=self.call(); self.announce(c,call)
        call['kind']='other'; call['_meta']={TOOL_IDENTITY:{'version':1,'kind':'builtin','name':'workspace_run'}}
        self.assertEqual(self.outcome(c,call),'cancelled')

    def test_legacy_requires_exact_native_envelope_and_title(self):
        for mutate in (
            lambda x: x['rawInput'].update(path='marker'),
            lambda x: x['rawInput'].pop('arguments'),
            lambda x: x['rawInput'].update(arguments=None),
            lambda x: x.update(title='workspace run'),
            lambda x: x.update(rawInput=['minecraft','observe']),
            lambda x: x['rawInput'].update(tool=['observe']),
        ):
            c = self.client(legacy=True); call = self.call(legacy=True); mutate(call)
            self.announce(c, call); self.assertEqual(self.outcome(c, call), 'cancelled')

    def test_legacy_direct_native_and_instance_backend_only(self):
        for name in ('agent-runtime', 'agent-instance', 'unknown'):
            c = self.client(legacy=True); c.info['agentInfo']['name'] = name
            c.info['_meta'] = {'io.github.bkrabach.agent-instance': {'backendAgentInfo': {'name':'agent-runtime'}}}
            call = self.call(legacy=True); self.announce(c, call)
            self.assertEqual(self.outcome(c, call), 'cancelled' if name == 'unknown' else 'selected')
        c.info['agentInfo']['name'] = 'agent-instance'
        c.info['_meta']['io.github.bkrabach.agent-instance']['backendAgentInfo']['name'] = 'unknown'
        self.assertEqual(self.outcome(c, call), 'cancelled')

    def test_advertised_identity_never_downgrades(self):
        for cap in (None, {}, {'version':True}, {'version':2}, {'version':'1'}, {'version':1,'extra':True}):
            c = self.client(); c.info['agentCapabilities']['_meta'][TOOL_IDENTITY] = cap
            call = self.call(legacy=True); self.announce(c, call)
            self.assertEqual(self.outcome(c, call), 'cancelled')
        for field in ('_meta', 'title', 'kind', 'rawInput'):
            c = self.client(); call = self.call(); self.announce(c, call)
            call.pop(field); self.assertEqual(self.outcome(c, call), 'cancelled')

    def test_malformed_or_unadvertised_metadata_never_authorizes(self):
        for value in (None, [], {}, {'version':True,'kind':'mcp','name':'observe','server':'minecraft'},
                      {'version':1,'kind':'mcp','name':'observe','server':'minecraft','extra':1},
                      {'version':1,'kind':'builtin','name':'observe','server':'minecraft'}):
            c=self.client(); call=self.call(); call['_meta'][TOOL_IDENTITY]=value
            self.announce(c,call); self.assertEqual(self.outcome(c,call),'cancelled')
        c=self.client(legacy=True); call=self.call(); self.announce(c,call)
        self.assertEqual(self.outcome(c,call),'cancelled')

    def test_request_cannot_replace_announced_identity_or_call(self):
        for field, value in (('toolCallId','other'), ('title','other'), ('kind','execute'),
                             ('rawInput',{'server':'minecraft','tool':'observe','arguments':{'x':1}}),
                             ('_meta',{TOOL_IDENTITY:{'version':1,'kind':'mcp','name':'move','server':'minecraft'}})):
            c=self.client(); call=self.call(); self.announce(c,call); call[field]=value
            self.assertEqual(self.outcome(c,call),'cancelled',field)
        c=self.client(); call=self.call()
        self.assertEqual(self.outcome(c,call),'cancelled')

    def test_session_change_does_not_reuse_an_old_announcement(self):
        c=self.client(); call=self.call(); self.announce(c,call)
        c.session='replacement-session'
        self.assertEqual(self.outcome(c,call,session='replacement-session'),'cancelled')

    def test_malformed_capability_container_cannot_downgrade(self):
        c=self.client(legacy=True); call=self.call(legacy=True); self.announce(c,call)
        for meta in (None, [], 'invalid'):
            c.info['agentCapabilities']['_meta']=meta
            self.assertEqual(self.outcome(c,call),'cancelled')

    def test_duplicate_ids_and_identity_updates_cannot_rebind(self):
        for update in ({'sessionUpdate':'tool_call'}, {'rawInput':{'server':'minecraft','tool':'move','arguments':{}}},
                       {'_meta':{TOOL_IDENTITY:None}}, {'title':'different'}):
            c=self.client(); call=self.call(); self.announce(c,call)
            c._record_tool_call({'sessionUpdate':'tool_call_update','toolCallId':'one',**update})
            self.assertEqual(self.outcome(c,call),'cancelled')
        c=self.client(); call=self.call(); self.announce(c,call)
        c._record_tool_call({'sessionUpdate':'tool_call_update','toolCallId':'one','status':'in_progress'})
        self.assertEqual(self.outcome(c,call),'selected')

    async def test_wrong_session_announcement_is_not_cached(self):
        from acp.schema import ToolCallStart
        c=self.client(); call=self.call()
        await _Callbacks(c).session_update('another-session', ToolCallStart.model_validate(call))
        self.assertEqual(self.outcome(c,call),'cancelled')

    def test_existing_authority_guards_and_terminal_calls_still_deny(self):
        for modify in (lambda c: setattr(c,'replaying',True),lambda c: setattr(c,'maintenance_active',True),
                       lambda c: setattr(c,'failed',RuntimeError('closed')),lambda c: setattr(c,'permission_active',lambda:False),
                       lambda c: setattr(c,'permission_tools',lambda:frozenset()),
                       lambda c: c.tool_calls['one'].update(status='completed')):
            c=self.client(); call=self.call(); self.announce(c,call); modify(c)
            self.assertEqual(self.outcome(c,call),'cancelled')
        c=self.client(); call=self.call(); self.announce(c,call)
        self.assertEqual(self.outcome(c,call,session='another-session'),'cancelled')
        self.assertEqual(self.outcome(c,call,options=[{'kind':'allow_always','optionId':'always'}]),'cancelled')


    def argument_client(self):
        c = self.client()
        c.info['agentInfo'] = {'name': 'agent-instance'}
        c.info['agentCapabilities']['_meta'][TOOL_IDENTITY] = {
            'version': 1, 'rawInputShape': 'arguments'}
        return c

    def argument_call(self, tool='inspect', arguments=None):
        call = self.call(tool)
        call.update(title='mcp_minecraft_' + tool, name='mcp_minecraft_' + tool,
                    kind='other', rawInput={} if arguments is None else arguments)
        return call

    def test_direct_arguments_require_explicit_negotiated_shape(self):
        for tool in GAME_TOOLS:
            c = self.argument_client(); call = self.argument_call(tool)
            self.announce(c, call)
            self.assertEqual(self.outcome(c, call), 'selected', tool)
        c = self.client(); call = self.argument_call()
        self.announce(c, call)
        self.assertEqual(self.outcome(c, call), 'cancelled')

    def test_direct_arguments_are_data_not_identity(self):
        for arguments in ({}, {'server':'filesystem','tool':'execute','arguments':{}},
                          {'_meta':{TOOL_IDENTITY:{'kind':'builtin'}},'name':'bash'}):
            c = self.argument_client(); call = self.argument_call(arguments=arguments)
            self.announce(c, call)
            self.assertEqual(self.outcome(c, call), 'selected')
        for value in (None, [], 'minecraft', 1):
            c = self.argument_client(); call = self.argument_call(); call['rawInput'] = value
            self.announce(c, call)
            self.assertEqual(self.outcome(c, call), 'cancelled')

    def test_direct_argument_names_and_titles_are_not_authority(self):
        c = self.argument_client(); call = self.argument_call()
        call.update(title='producer display label', name='informational only')
        self.announce(c, call)
        self.assertEqual(self.outcome(c, call), 'selected')
        for identity in ({'version':1,'kind':'builtin','name':'bash'},
                         {'version':1,'kind':'caller','name':'inspect','server':'minecraft'},
                         {'version':1,'kind':'mcp','name':'inspect','server':'filesystem'},
                         {'version':1,'kind':'mcp','name':'arbitrary_host_command','server':'minecraft'}):
            c = self.argument_client(); call = self.argument_call()
            call['_meta'][TOOL_IDENTITY] = identity
            self.announce(c, call)
            self.assertEqual(self.outcome(c, call), 'cancelled')

    def test_direct_argument_shape_capability_never_downgrades(self):
        for cap in ({'version':1,'rawInputShape':'unknown'},
                    {'version':1,'rawInputShape':None}, {'version':1,'rawInputShape':True},
                    {'version':True,'rawInputShape':'arguments'},
                    {'version':2,'rawInputShape':'arguments'},
                    {'version':1,'rawInputShape':'arguments','extra':True},
                    {'rawInputShape':'arguments'}):
            for direct in (False, True):
                c = self.argument_client()
                c.info['agentCapabilities']['_meta'][TOOL_IDENTITY] = cap
                call = self.argument_call() if direct else self.call()
                self.announce(c, call)
                self.assertEqual(self.outcome(c, call), 'cancelled', cap)
        c = self.argument_client(); del c.info['agentCapabilities']['_meta'][TOOL_IDENTITY]
        call = self.argument_call(); self.announce(c, call)
        self.assertEqual(self.outcome(c, call), 'cancelled')

    def test_direct_argument_request_must_match_complete_announcement(self):
        for field in ('title', 'rawInput', '_meta'):
            c = self.argument_client(); call = self.argument_call(); self.announce(c, call)
            call.pop(field)
            self.assertEqual(self.outcome(c, call), 'cancelled', field)
        for field, value in (('toolCallId','different'),('title','different'),
                             ('rawInput',{'changed':True}),
                             ('_meta',{TOOL_IDENTITY:{'version':1,'kind':'mcp','name':'observe','server':'minecraft'}})):
            c = self.argument_client(); call = self.argument_call(); self.announce(c, call)
            call[field] = value
            self.assertEqual(self.outcome(c, call), 'cancelled', field)

    def test_direct_argument_guards_remain_authoritative(self):
        for modify in (lambda c:setattr(c,'replaying',True),
                       lambda c:setattr(c,'maintenance_active',True),
                       lambda c:setattr(c,'permission_active',lambda:False),
                       lambda c:setattr(c,'permission_tools',lambda:frozenset()),
                       lambda c:setattr(c,'failed',RuntimeError('closed')),
                       lambda c:c.tool_calls['one'].update(status='completed')):
            c = self.argument_client(); call = self.argument_call(); self.announce(c, call); modify(c)
            self.assertEqual(self.outcome(c, call), 'cancelled')
        c = self.argument_client(); call = self.argument_call(); self.announce(c, call)
        self.assertEqual(self.outcome(c,call,session='other-session'),'cancelled')
        self.assertEqual(self.outcome(c,call,options=[{'kind':'allow_always','optionId':'always'}]),'cancelled')

    def test_permission_payload_comparison_preserves_nested_json_types(self):
        for direct in (False, True):
            for original, changed in ((True, 1), (False, 0), (1, True), (1, 1.0)):
                c = self.argument_client() if direct else self.client()
                arguments = {'nested': [{'value': original}]}
                call = self.argument_call(arguments=arguments) if direct else self.call(arguments=arguments)
                self.announce(c, call)
                altered = copy.deepcopy(call)
                raw = altered['rawInput'] if direct else altered['rawInput']['arguments']
                raw['nested'][0]['value'] = changed
                self.assertEqual(self.outcome(c, altered), 'cancelled', (direct, original, changed))
        c = self.argument_client(); call = self.argument_call(arguments={'a':1,'b':{'x':True,'y':2}})
        self.announce(c,call)
        call['rawInput'] = {'b':{'y':2,'x':True},'a':1}
        self.assertEqual(self.outcome(c,call),'selected')

    def test_type_changing_progress_update_invalidates_identity(self):
        c = self.argument_client(); call = self.argument_call(arguments={'values':[True]})
        self.announce(c, call)
        c._record_tool_call({'sessionUpdate':'tool_call_update','toolCallId':'one','rawInput':{'values':[1]}})
        self.assertEqual(self.outcome(c, call), 'cancelled')

    async def test_direct_argument_official_sdk_callback_preserves_identity(self):
        from acp.schema import ToolCallStart, ToolCallUpdate, PermissionOption
        c = self.argument_client(); call = self.argument_call(arguments={'summary':'fixture'})
        await _Callbacks(c).session_update(c.session, ToolCallStart.model_validate(call))
        request = {k:v for k,v in call.items() if k not in ('sessionUpdate','status','name')}
        result = await _Callbacks(c).request_permission(c.session,ToolCallUpdate.model_validate(request),
            [PermissionOption(kind='allow_once',optionId='once',name='Allow')])
        self.assertEqual(wire(result)['outcome']['outcome'],'selected')

if __name__ == '__main__':
    unittest.main()
