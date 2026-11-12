"""Official SDK rejection peer; no provider, game or credential access."""
import asyncio
import json
import os
from acp import Agent, InitializeResponse, NewSessionResponse, PromptResponse, run_agent
from acp.exceptions import RequestError

META = 'com.microsoft.amplifier.attention'


class Peer(Agent):
    def __init__(self):
        self.release = asyncio.Event()

    async def initialize(self, protocol_version, **kwargs):
        return InitializeResponse(protocol_version=protocol_version, field_meta={META: {
            'version': 1, 'enabled': True, 'method': '_amplifier/attention',
            'promptMetadata': META, 'noForwardRejectionVersion': 1}})

    async def new_session(self, cwd, **kwargs):
        return NewSessionResponse(session_id='original-session')

    def reject(self, mode, session_id, offer):
        if mode == 'closed':
            os._exit(0)
        receipt = {'version': 1, 'id': offer.get('id', 'unoffered'),
                   'sessionId': session_id, 'outcome': 'not_forwarded'}
        if mode == 'wrong-offer': receipt['id'] = 'another-offer'
        if mode == 'wrong-session': receipt['sessionId'] = 'another-session'
        if mode == 'future-version': receipt['version'] = 2
        if mode == 'bool-version': receipt['version'] = True
        if mode == 'float-version': receipt['version'] = 1.0
        if mode == 'wrong-outcome': receipt['outcome'] = 'incorporated'
        data = {META: receipt, 'privateDetail': 'never-log-error-data'}
        if mode == 'missing': data = None
        if mode == 'wrong-type': data = {META: ['not_forwarded']}
        if mode == 'unrelated-response':
            # Deliberately inject a wrong JSON-RPC ID. Only the upstream SDK may
            # correlate it; the adapter must use the matching ordinary error.
            print(json.dumps({'jsonrpc': '2.0', 'id': 'unrelated-request', 'error': {
                'code': -32002, 'message': 'private stray response', 'data': data}}), flush=True)
            data = None
        code = -32603 if mode == 'other-code' else -32002
        raise RequestError(code, 'never-log-private-error-or-ticket', data)

    async def prompt(self, session_id, prompt, **kwargs):
        mode = prompt[-1].text
        if mode == 'independent':
            return PromptResponse(stop_reason='end_turn')
        if mode.startswith('gated-'):
            await self.release.wait()
            mode = mode.removeprefix('gated-')
        self.reject(mode, session_id, kwargs.get(META, {}))

    async def ext_method(self, method, params):
        if method == 'test/release':
            self.release.set()
            return {}
        self.reject(params.get('fixtureMode', 'valid'), params['sessionId'],
                    params.get('_meta', {}).get(META, {}))


asyncio.run(run_agent(Peer()))
