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


def ordinary_sources(info):
    cap = mapping(mapping(instance(info).get('inputContinuity')).get('sourceDelivery'))
    return (source_delivery(info) and cap.get('ordinaryPrompts') is True
            and cap.get('promptRetry') == 'inspectOnly')


def ordinary_metadata(info, value):
    """Validate the negotiated wire shape; never infer a source from prompt text."""
    v = mapping(value)
    facts = sources(v.get('sources'))
    identity = v.get('inputId')
    if (not ordinary_sources(info) or set(v) != {'version', 'inputId', 'sources'}
            or type(v.get('version')) is not int or v['version'] != 1
            or not isinstance(identity, str) or not 1 <= len(identity.encode()) <= 512
            or not facts):
        raise ValueError('Ordinary source metadata is invalid or not negotiated')
    return {'version': 1, 'inputId': identity, 'sources': facts}


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
