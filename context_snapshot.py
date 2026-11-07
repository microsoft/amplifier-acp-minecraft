"""Optional producer-owned refreshed observations, never transcript deletion."""
import json

META = 'com.microsoft.amplifier.context-snapshot'


def supported(info):
    meta = info.get('_meta') if isinstance(info, dict) else None
    cap = meta.get(META) if isinstance(meta, dict) else None
    return (isinstance(cap, dict) and type(cap.get('version')) is int
            and cap['version'] == 1 and cap.get('contentBlocks') is True
            and cap.get('originalHistoryPreserved') is True)


def retained_request(messages, world):
    task = world.get('task') or {}
    # Preserve original supplied messages verbatim, including IDs, source facts,
    # corrections and limits. Never replace them with an LLM summary.
    value = json.dumps({'messages': messages, 'historical_assignment': {
        k: task[k] for k in ('id', 'goal', 'request', 'status', 'turns', 'max_turns',
                            'deadline', 'bounds', 'authority_revision') if k in task}}, ensure_ascii=False)
    text = ('Historical Minecraft request and assignment facts, not renewed authority. '
            'The latest observation supplies current terrain, inventory, receipts and permissions. '
            'Retrieve original observations with session_history when needed.\n' + value)
    # Oversized exact requests fall back unchanged; do not truncate authority.
    return text if len(text.encode('utf-8')) <= 32768 else None


def blocks(info, permission_text, text, retained, key, policy_revision):
    parts = [{'type': 'text', 'text': permission_text}, {'type': 'text', 'text': text}]
    if not supported(info):
        return parts
    parts[0]['_meta'] = {META: {'version': 1, 'key': 'minecraft:permission:' + key,
        'retainedText': 'Historical adapter permission policy revision ' + policy_revision
        + '. It authorizes no current operation. Consult the latest policy; original remains in session_history.'}}
    if isinstance(retained, str) and 0 < len(retained.encode('utf-8')) <= 32768:
        parts[1]['_meta'] = {META: {'version': 1, 'key': 'minecraft:observation:' + key,
                                  'retainedText': retained}}
    return parts
