"""Official-SDK peer; disposable, no provider, credentials or Minecraft access."""
import asyncio
import json
import sys
from acp import Agent, InitializeResponse, NewSessionResponse, PromptResponse, run_agent
from acp.schema import AgentCapabilities, AgentMessageChunk, TextContentBlock, LoadSessionResponse
from acp.exceptions import RequestError


class Peer(Agent):
    def on_connect(self, connection):
        self.connection = connection
        self.release = asyncio.Event()

    async def initialize(self, protocol_version, **kwargs):
        return InitializeResponse(protocol_version=protocol_version,
                                  agent_capabilities=AgentCapabilities(load_session=True),
                                  field_meta=({'com.microsoft.amplifier.context-snapshot': {
                                      'version': 1, 'contentBlocks': True, 'originalHistoryPreserved': True}}
                                      if 'snapshots' in sys.argv else None))

    async def new_session(self, cwd, **kwargs):
        return NewSessionResponse(session_id='sdk-session')

    async def load_session(self, session_id, cwd, **kwargs):
        await self.chunk(session_id, 'archived')
        return LoadSessionResponse()

    async def chunk(self, session_id, text, message_id=None, meta=None):
        await self.connection.session_update(session_id=session_id, update=AgentMessageChunk(
            content=TextContentBlock(text=text), message_id=message_id, field_meta=meta))

    async def prompt(self, session_id, prompt, **kwargs):
        mode = prompt[-1].text
        if mode == 'snapshot-wire':
            await self.chunk(session_id, json.dumps([p.model_dump(by_alias=True, exclude_none=True) for p in prompt]))
        elif mode == 'fail':
            raise RequestError(-32001, 'private error must not appear in adapter diagnostics')
        elif mode == 'filesystem':
            try:
                await self.connection.read_text_file(session_id=session_id, path='/must-not-read')
                raise AssertionError('Unadvertised filesystem callback allowed')
            except RequestError as error:
                await self.chunk(session_id, str(error.code))
        elif mode == 'wrong-session':
            await self.chunk('other', 'private')
        elif mode == 'oversize':
            await self.chunk(session_id, 'x' * 250001)
        elif mode == 'blocked':
            await self.chunk(session_id, 'first')
            await self.chunk(session_id, 'queued')
            await self.release.wait()
        elif mode == 'concurrent':
            await self.chunk(session_id, 'ready')
            await self.release.wait()
            await self.chunk(session_id, ' done')
        else:
            await self.chunk(session_id, 'old', 'old')
            await self.chunk(session_id, 'new', 'new', {'com.microsoft.amplifier.message': {'phase': 'final_answer'}})
            await self.chunk(session_id, ' tail', 'old')
            await self.chunk(session_id, '', meta={'inputReceipt': {'state': 'received'}})
        return PromptResponse(stop_reason='end_turn')

    async def ext_method(self, method, params):
        if method == 'test/release':
            self.release.set()
            return {'source': params, 'state': 'received'}
        raise RequestError.method_not_found(method)

    async def cancel(self, session_id, **kwargs):
        self.release.set()


asyncio.run(run_agent(Peer()))
