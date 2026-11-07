"""Controller settlement acknowledgment; no session/task/world mutations."""
import os
from pathlib import Path
from installation_guard import read, durable_write, ContinuityError


def process_identity(pid):
    # stat's parenthesized comm may itself contain spaces/parentheses.
    stat = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
    return {'pid': int(pid), 'start_ticks': stat[19],
            'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip()}


def held(home, *, acknowledge=False):
    root = Path(home)/'installation-updates'
    try:
        gate = read(root/'gate.json')
    except FileNotFoundError:
        return False
    if (gate.get('version') != 1 or gate.get('closed') is not True
            or not isinstance(gate.get('transaction_id'), str) or not gate['transaction_id']):
        raise ContinuityError('Malformed installation admission gate')
    if acknowledge:
        # Called only outside any controller iteration, after prompt/sequence
        # settlement. PID plus boot/start identity protects against PID reuse.
        durable_write(root/'controller-idle.json',
                      {'transaction_id': gate['transaction_id'], **process_identity(os.getpid())})
    return True
