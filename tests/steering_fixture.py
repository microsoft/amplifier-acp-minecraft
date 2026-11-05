"""An independent ACP peer exercising concurrent prompts, callbacks and receipts."""
import json
import sys

mode = sys.argv[1]
sid = 'saved-agent'
active = None
steered = False
permission = False
receipts = []


def send(value):
    print(json.dumps({'jsonrpc': '2.0', **value}), flush=True)


def update(item):
    send({'method': 'session/update', 'params': {'sessionId': sid, 'update': item}})


def finish():
    global active
    if active is not None and steered and permission:
        update({'sessionUpdate': 'tool_call_update', 'toolCallId': 'inspect', 'status': 'completed'})
        update({'sessionUpdate': 'agent_message_chunk', 'content': {'type': 'text', 'text': 'Fresh peer evidence received.'}})
        send({'id': active, 'result': {'stopReason': 'end_turn'}})
        active = None


for line in sys.stdin:
    message = json.loads(line)
    method = message.get('method')
    if method == 'initialize':
        send({'id': message['id'], 'result': {'protocolVersion': 1,
              'agentInfo': {'name': 'codex' if mode == 'codex' else 'native'},
              'agentCapabilities': {'loadSession': True}, '_meta': {
                  'steering': {'supported': True, **({} if mode == 'codex' else {'receiptsMethod': '_session/input_receipts'})}, 'io.github.bkrabach.agent-instance': {
                      'inputContinuity': {'awareness': {'version': 1, 'activeOnly': True, 'promptIdRequired': True}}}}}})
    elif method == 'session/new':
        send({'id': message['id'], 'result': {'sessionId': sid}})
    elif method == 'session/prompt':
        active = message['id']
        update({'sessionUpdate': 'tool_call', 'toolCallId': 'inspect', 'status': 'pending',
                'rawInput': {'server': 'minecraft', 'tool': 'conversation'}})
        send({'id': 'permission', 'method': 'session/request_permission', 'params': {
            'sessionId': sid, 'toolCall': {'toolCallId': 'inspect'},
            'options': [{'kind': 'allow_once', 'optionId': 'once'}]}})
    elif message.get('id') == 'permission':
        assert message['result']['outcome'] == {'outcome': 'selected', 'optionId': 'once'}
        permission = True
        finish()
    elif method == '_session/steering':
        meta = message['params']['_meta']['steering']
        assert meta['intent'] == 'awareness' and meta['idleBehavior'] == 'promptRequired'
        if active is None or active != meta['activePromptId']:
            send({'id': message['id'], 'result': {'outcome': 'promptRequired', 'reason': 'noMatchingActivePrompt'}})
        else:
            steered = True
            receipts.append({'inputId': meta['inputId'], 'state': 'incorporated', 'recorded': True, 'sequence': len(receipts)})
            # A prompt result can precede its steering reply, without confusing IDs.
            finish()
            if mode != 'lost':
                send({'id': message['id'], 'result': {'outcome': 'injected'}})
    elif method == '_session/input_receipts':
        if mode == 'codex':
            send({'id': message['id'], 'error': {'code': -32601}})
        else:
            send({'id': message['id'], 'result': {'inputReceipts': receipts}})
    elif method == 'session/cancel':
        if active is not None:
            send({'id': active, 'result': {'stopReason': 'cancelled'}})
            active = None
    else:
        send({'id': message.get('id'), 'error': {'code': -32601}})
