#!/usr/bin/env python3
"""Overlay only the reviewed LAN classes onto an exact official Geyser artifact.

Build the adjacent patch first; this does not download, install, restart or edit
configuration. It refuses unknown bases and preserves every unrelated ZIP entry.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import zipfile

BASE_COMMIT = '50360e396b08c10dac4dfb78213dcb0126b75f90'
BASES = {
    'velocity': '945a7ece089f44118ba85848ceb7a6e054fe65c26f5525dd7f548b44e5b42175',
    'standalone': 'fcd8cd26f3e4a1180ee3828b6c63ed3b90e78c99c7ccc2cbba3b12f303d705b9',
}
PREFIXES = (
    'org/geysermc/geyser/network/bedrock/nethernet/NetherNetServer',
    'org/geysermc/geyser/network/bedrock/nethernet/UnsignedAnswerSignaling',
    'org/geysermc/geyser/network/bedrock/nethernet/LanLoginPolicy',
    'org/geysermc/geyser/session/auth/BedrockClientData',
    'org/geysermc/geyser/util/LoginEncryptionUtils',
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def overlay(base, built, output, expected):
    base, built, output = map(Path, (base, built, output))
    if output.resolve() in (base.resolve(), built.resolve()) or output.exists():
        raise ValueError('Output must be a new file, separate from both inputs')
    data = base.read_bytes()
    if sha(data) != expected:
        raise ValueError('Official base SHA256 mismatch; do not patch another release')
    with zipfile.ZipFile(base) as original, zipfile.ZipFile(built) as compiled:
        for archive in (original, compiled):
            if len(archive.namelist()) != len(set(archive.namelist())):
                raise ValueError('Duplicate ZIP entries')
        changes = {n: compiled.read(n) for n in compiled.namelist()
                   if n.endswith('.class') and any(n == p+'.class' or n.startswith(p+'$') for p in PREFIXES)}
        if any(p+'.class' not in changes for p in PREFIXES):
            raise ValueError('Missing required compiled patch class')
        if 'constellation-lan-patch.json' in original.namelist():
            raise ValueError('Base already patched')
        receipt = {'base_source': BASE_COMMIT, 'base_sha256': expected,
                   'class_sha256': {n: sha(d) for n, d in sorted(changes.items())},
                   'all_other_original_entries_byte_exact': True}
        with tempfile.NamedTemporaryFile(dir=output.parent, suffix='.jar', delete=False) as stream:
            temporary = Path(stream.name)
        try:
            with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED) as target:
                for entry in original.infolist():
                    target.writestr(copy.copy(entry), changes.get(entry.filename, original.read(entry.filename)))
                for name in sorted(set(changes)-set(original.namelist())):
                    target.writestr(name, changes[name])
                target.writestr('constellation-lan-patch.json', json.dumps(receipt, sort_keys=True))
            with zipfile.ZipFile(temporary) as target:
                if any(original.read(n) != target.read(n) for n in original.namelist() if n not in changes):
                    raise ValueError('Unexpected unrelated artifact change')
                if any(target.read(n) != value for n, value in changes.items()):
                    raise ValueError('Compiled class mismatch')
            # Exclusive output creation: never replace another build or live JAR.
            with output.open('xb') as target:
                target.write(temporary.read_bytes())
        finally:
            temporary.unlink(missing_ok=True)
    return {**receipt, 'output_sha256': sha(output.read_bytes()), 'output': str(output)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--platform', required=True, choices=BASES)
    p.add_argument('--base', type=Path, required=True)
    p.add_argument('--built', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(overlay(args.base, args.built, args.out, BASES[args.platform]), indent=2))


if __name__ == '__main__':
    main()
