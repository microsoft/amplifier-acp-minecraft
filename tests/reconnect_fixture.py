"""Deterministic ACP process lifecycle fixture; no model or Minecraft connection."""
import json
from pathlib import Path
import sys

root, scenario = Path(sys.argv[1]), sys.argv[2]
counter = root / 'launches'
launch = int(counter.read_text()) + 1 if counter.exists() else 1
counter.write_text(str(launch))

def send(value):
    print(json.dumps({'jsonrpc': '2.0', **value}), flush=True)

for line in sys.stdin:
    value = json.loads(line)
    method = value.get('method')
    with (root / 'requests.jsonl').open('a') as log:
        log.write(json.dumps({'launch': launch, 'method': method,
                              'session': value.get('params', {}).get('sessionId'),
                              'mcp_names': [s['name'] for s in value.get('params', {}).get('mcpServers', [])]}) + '\n')
    if method == 'initialize':
        result = {'protocolVersion': 1,
                  'agentCapabilities': {'loadSession': True, 'mcpCapabilities': {'http': True}}}
        if scenario.startswith('resume-'):
            result['agentCapabilities'].update(loadSession=False, sessionCapabilities={'resume': {}})
        send({'id': value['id'], 'result': result})
    elif method == 'session/new':
        if scenario == 'lost-new-result':
            break
        send({'id': value['id'], 'result': {'sessionId': 'durable-session'}})
    elif method in ('session/load', 'session/resume'):
        if scenario in ('reload-fails', 'resume-fails'):
            send({'id': value['id'], 'error': {'code': -32000, 'message': 'Fixture reload failure'}})
        else:
            send({'id': value['id'], 'result': {}})
    elif method == 'session/prompt':
        if scenario == 'during-prompt':
            send({'method': 'session/update', 'params': {'sessionId': 'durable-session',
                  'update': {'sessionUpdate': 'tool_call', 'toolCallId': 'unfinished',
                             'status': 'in_progress', 'title': 'Fixture action'}}})
            break
        send({'id': value['id'], 'result': {'stopReason': 'end_turn'}})
        if scenario != 'keep-open':
            break
