"""Read-only inventory validation shared by the package launcher and updater."""
import hashlib
import json
import os
from pathlib import Path


def validate(root):
    manifest=json.loads((root/'manifest.json').read_text())
    if manifest.get('schema')!=1:
        raise ValueError('Unsupported package manifest')
    for command in ('python','node','task_helper'):
        if manifest.get('commands',{}).get(command) not in manifest['files']:
            raise ValueError('Runtime command is not an inventoried package file')
    for name,entry in manifest['files'].items():
        relative=Path(name)
        if relative.is_absolute() or '..' in relative.parts or '\\' in name or ':' in name:
            raise ValueError('Unsafe package path')
        path=root/relative
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError('Package path escapes its root')
        if 'link' in entry:
            if not path.is_symlink() or os.readlink(path)!=entry['link']:
                raise ValueError('Package link changed: '+name)
        elif path.is_symlink() or not path.is_file() or path.stat().st_size!=entry['size']:
            raise ValueError('Package file changed: '+name)
        else:
            with path.open('rb') as stream:
                if hashlib.file_digest(stream,'sha256').hexdigest()!=entry['sha256']:
                    raise ValueError('Package digest changed: '+name)
    return manifest

