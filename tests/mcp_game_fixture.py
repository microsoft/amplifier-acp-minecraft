"""Call the disposable fixture body's public Minecraft MCP tools."""
import json
import urllib.request
import uuid


class GameToolError(Exception):
    def __init__(self, result):
        self.result = result
        super().__init__(result.get('error', 'Minecraft tool refused'))


def call_tool(cfg, name, arguments):
    """One request, one effect ID. A lost transport response is never retried."""
    arguments = dict(arguments)
    identifier = str(uuid.uuid4())
    if name not in {'observe', 'conversation', 'entities', 'inventory', 'inspect', 'read_sign',
                    'survey', 'map', 'plan_route', 'find', 'legacy_work', 'operation_status',
                    'stop', 'cancel_movement'}:
        arguments.setdefault('operation_id', identifier)
    call = {'jsonrpc': '2.0', 'id': identifier, 'method': 'tools/call',
            'params': {'name': name, 'arguments': arguments}}
    request = urllib.request.Request(f"http://127.0.0.1:{cfg['control_port']}/mcp",
        data=json.dumps(call).encode(), headers={'Content-Type':'application/json',
        'Accept':'application/json, text/event-stream','Authorization':'Bearer ' + cfg['token']})
    with urllib.request.urlopen(request, timeout=70) as response:
        reply = json.load(response)
    if reply.get('id') != identifier or 'error' in reply:
        raise ValueError('MCP request failed or response ID did not match')
    result = reply['result']
    text = result['content'][0]['text']
    if result.get('isError'):
        try:
            error = json.loads(text)
        except ValueError:
            error = {'error': text}
        raise GameToolError(error)
    return json.loads(text)
