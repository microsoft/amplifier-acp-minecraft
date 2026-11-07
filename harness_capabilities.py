"""Strict optional Instance contracts. Unknown/absent capability stays plain ACP."""
INSTANCE = 'io.github.bkrabach.agent-instance'
SOURCE_META = 'com.microsoft.amplifier.source-delivery'
SOURCE_METHOD = '_amplifier/source_receipts'
MAINTENANCE_META = 'com.microsoft.amplifier.maintenance'


def mapping(value):
    return value if isinstance(value, dict) else {}


def instance(info):
    return mapping(mapping(mapping(info).get('_meta')).get(INSTANCE))


def source_delivery(info):
    cap = mapping(mapping(instance(info).get('inputContinuity')).get('sourceDelivery'))
    return (type(cap.get('version')) is int and cap['version'] == 1
            and cap.get('metadata') == SOURCE_META and cap.get('receiptsMethod') == SOURCE_METHOD)


def maintenance(info):
    cap = mapping(instance(info).get('maintenance'))
    return (type(cap.get('version')) is int and cap['version'] == 1
            and cap.get('promptMetadata') == MAINTENANCE_META
            and cap.get('requiresAdvertisedCommand') is True)


def sources(values):
    """Validate existing source facts. Never replace original time with now."""
    if not isinstance(values, list) or not 1 <= len(values) <= 40:
        return []
    result, seen = [], set()
    for value in values:
        v = mapping(value)
        identity, revision, occurred = v.get('id'), v.get('revision'), v.get('occurredAt')
        if (not isinstance(identity, str) or not 1 <= len(identity.encode()) <= 512
                or not isinstance(revision, str) or not 1 <= len(revision.encode()) <= 128
                or type(occurred) is not int or occurred <= 0 or identity in seen):
            return []
        seen.add(identity)
        result.append({'id': identity, 'revision': revision, 'occurredAt': occurred})
    return result


def attention_context(context, source_facts, info):
    """Old strict schemas get exactly the old message fields."""
    if not source_delivery(info):
        return context
    by_id = {s['id']: s for s in sources(source_facts)}
    result = dict(context)
    result['messages'] = []
    for message in context.get('messages', []):
        item = dict(message)
        if (source := by_id.get(item.get('id'))) is not None:
            item.update(revision=source['revision'], occurred_at=source['occurredAt'])
        result['messages'].append(item)
    return result


ATTENTION_META = 'com.microsoft.amplifier.attention'
ATTENTION_METHOD = '_amplifier/attention'
def attention(info):
    cap=mapping(mapping(info).get('_meta')).get(ATTENTION_META)
    cap=mapping(cap)
    return cap if type(cap.get('version')) is int and cap['version']==1 and cap.get('enabled') is True and cap.get('method')==ATTENTION_METHOD else {}

def activity(info):
    cap=mapping(attention(info).get('activity'))
    return (type(cap.get('version')) is int and cap['version']==1
            and cap.get('contextField')=='activities' and type(cap.get('maxItems')) is int
            and 1 <= cap['maxItems'] <= 16)

def human_messages(info):
    cap=mapping(attention(info).get('humanMessages'))
    return type(cap.get('version')) is int and cap['version']==1 and cap.get('budgetPolicy')=='independent_of_ambient'
