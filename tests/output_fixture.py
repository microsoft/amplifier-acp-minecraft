"""Disposable ACP endpoint exercising the released message identity wire shape."""
import json
import sys

mode = sys.argv[1]


def emit(value):
    print(json.dumps({'jsonrpc': '2.0', **value}), flush=True)


def chunk(ident, text, phase=None):
    update = {'sessionUpdate': 'agent_message_chunk', 'content': {'type': 'text', 'text': text}}
    if ident is not None:
        update['messageId'] = ident
    if phase is not None:
        update['_meta'] = {'com.microsoft.amplifier.message': {'phase': phase}}
    return update


def updates():
    revised = [chunk('draft', 'Need sticks.', 'final_answer'),
               chunk('new', 'Sticks already ', 'final_answer'),
               chunk('draft', ' Please send some.', 'final_answer'),
               chunk('new', 'delivered.'),
               chunk('status', 'Checking receipts.', 'commentary')]
    tool = {'sessionUpdate': 'tool_call', 'toolCallId': 'inspect', 'status': 'in_progress', 'title': 'Inspect'}
    tool_done = {'sessionUpdate': 'tool_call_update', 'toolCallId': 'inspect', 'status': 'completed'}
    media = {'sessionUpdate': 'agent_message_chunk', 'messageId': 'picture',
             'content': {'type': 'image', 'mimeType': 'image/png', 'data': 'fixture'}}
    if mode == 'empty':
        return revised + [chunk('empty', '', 'final_answer')]
    if mode == 'pass':
        return [chunk('old', '{"decision":"speak","text":"Need sticks"}', 'final_answer'),
                chunk('revised', '{"decision":"pass",', 'final_answer'),
                chunk('old', ' '), chunk('revised', '"reason":"peer answered"}')]
    if mode == 'legacy':
        return [chunk(None, 'One '), chunk(None, 'plain answer.')]
    if mode == 'legacy_tools':
        return [chunk(None, 'Before.'), tool, media, tool_done, chunk(None, 'After '), chunk(None, 'tools.')]
    if mode == 'additive':
        return [chunk('old', 'Before.'), tool, chunk('new', 'Current '), media,
                chunk('old', ' late tail.'), chunk('new', 'answer.')]
    if mode == 'optional_phase':
        return [chunk('provider-item', 'Old.'), chunk('stable-call-UUID', 'Current '),
                chunk('provider-item', ' late tail.'), chunk('stable-call-UUID', 'answer.')]
    if mode == 'commentary_only':
        return [chunk('comment', 'Looking ', 'commentary'), chunk('comment', 'around.'),
                chunk('empty', '', 'final_answer')]
    if mode == 'empty_first':
        return [chunk('old', ''), chunk('new', 'Current.'), chunk('old', 'Late old text.')]
    if mode == 'mixed':
        return [chunk(None, 'Legacy.'), chunk('new', 'Current.'), chunk(None, ' Older tail.')]
    if mode == 'metadata':
        a, b = chunk('current', 'Current '), chunk('current', 'answer.')
        a['_meta'] = None
        b['_meta'] = {'com.microsoft.amplifier.message': 'unrecognized'}
        return [a, b]
    if mode == 'identity_limit':
        return [chunk(str(i), '') for i in range(1025)]
    if mode == 'phase_change':
        return [chunk('old', 'Old.'), chunk('new', 'Current ', 'commentary'),
                chunk('new', 'answer.', 'final_answer'), chunk('old', ' late tail.')]
    return revised


for line in sys.stdin:
    request = json.loads(line)
    method = request.get('method')
    if method == 'initialize':
        result = {'protocolVersion': 1, 'agentCapabilities': {'loadSession': True}}
    elif method == 'session/new':
        result = {'sessionId': 'output-test'}
    elif method in ('session/prompt', 'session/load'):
        for update in updates() if method == 'session/prompt' else [chunk('new', 'Saved history.', 'final_answer')]:
            emit({'method': 'session/update', 'params': {'sessionId': 'output-test', 'update': update}})
        result = {'stopReason': 'end_turn'} if method == 'session/prompt' else {}
    else:
        result = {}
    emit({'id': request['id'], 'result': result})
