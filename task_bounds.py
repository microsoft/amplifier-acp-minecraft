"""Read explicit assignment limits; absent or unknown values never mean unlimited."""
import time


def allowance_remaining(task, now_ms=None):
    now_ms = time.time()*1000 if now_ms is None else now_ms
    turns = task.get('turns')
    if type(turns) is not int or turns < 0:
        return False
    bounds = task.get('bounds')
    if 'bounds' not in task:
        return (type(task.get('deadline')) is int and task['deadline'] > now_ms
                and type(task.get('max_turns')) is int and task['max_turns'] > turns)
    if not isinstance(bounds, dict) or type(bounds.get('version')) is not int or bounds.get('version') != 1 or set(bounds) != {'version', 'deadline_ms', 'max_turns'}:
        return False
    for key, field, used in [('deadline_ms', 'deadline', now_ms), ('max_turns', 'max_turns', turns)]:
        bound = bounds[key]
        if not isinstance(bound, dict):
            return False
        if bound == {'kind': 'no_configured_bound'}:
            if field in task:
                return False
        elif (set(bound) == {'kind', 'value'} and bound.get('kind') == 'finite'
              and type(bound.get('value')) is int and bound['value'] >= 0
              and type(task.get(field)) is int and task[field] == bound['value']):
            if bound['value'] <= used:
                return False
        else:
            return False
    return True
