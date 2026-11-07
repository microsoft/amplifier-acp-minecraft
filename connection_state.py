"""Persistent owner connection intent; never task authority or an agent tool."""
from pathlib import Path
from installation_guard import read, ContinuityError


def state(home):
    try:
        value = read(Path(home)/'installation-connections/state.json')
    except FileNotFoundError:
        return None
    if (value.get('schema') != 1 or value.get('phase') not in
            ('disconnecting', 'disconnected', 'connecting', 'connected')
            or not isinstance(value.get('request_id'), str)):
        raise ContinuityError('Invalid saved connection intent')
    return value


def deferred(home):
    value = state(home)
    return value is not None and value['phase'] != 'connected'
