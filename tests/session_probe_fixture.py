"""Official SDK peer recording only disposable session compatibility checks."""
import asyncio
import json
import os
from pathlib import Path
from acp import Agent, InitializeResponse, run_agent
from acp.schema import AgentCapabilities, LoadSessionResponse
from acp.exceptions import RequestError


class Peer(Agent):
    def record(self, action, **data):
        with Path(os.environ['PROBE_LOG']).open('a') as f:
            f.write(json.dumps({'action':action, **data})+'\n')

    async def initialize(self, protocol_version, **kwargs):
        self.record('initialize')
        mode = os.environ.get('PROBE_MODE')
        if mode == 'initialize-error':
            raise RequestError(-32603, 'Initialization unavailable')
        if mode == 'initialize-slow':
            await asyncio.sleep(60)
        return InitializeResponse(protocol_version=protocol_version,
            agent_capabilities=AgentCapabilities(load_session=os.environ.get('PROBE_MODE')!='unsupported'))

    async def load_session(self, session_id, cwd, **kwargs):
        self.record('load', session=session_id)
        mode = os.environ.get('PROBE_MODE')
        if mode == 'missing':
            raise RequestError(-32002, 'Original session unavailable')
        if mode == 'slow':
            await asyncio.sleep(60)
        return LoadSessionResponse()

    async def new_session(self, **kwargs):
        self.record('FORBIDDEN_new')
        raise AssertionError('Must not create a session')

    async def prompt(self, **kwargs):
        self.record('FORBIDDEN_prompt')
        raise AssertionError('Must not prompt')


asyncio.run(run_agent(Peer()))
