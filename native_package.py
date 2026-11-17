"""Read-only inventory validation shared by the package launcher and updater."""
import hashlib
import json
import os
import stat
from pathlib import Path


def validate(root):
    manifest=json.loads((root/'manifest.json').read_text())
    if manifest.get('schema')!=1:
        raise ValueError('Unsupported package manifest')
    for command in ('python','node','task_helper'):
        if manifest.get('commands',{}).get(command) not in manifest['files']:
            raise ValueError('Runtime command is not an inventoried package file')
    # Anchor containment once per validation, but resolve every entry afresh.
    # Content hashes are always read; no validation survives across calls.
    canonical_root=root.resolve()
    for name,entry in manifest['files'].items():
        relative=Path(name)
        if relative.is_absolute() or '..' in relative.parts or '\\' in name or ':' in name:
            raise ValueError('Unsafe package path')
        path=root/relative
        if not path.resolve().is_relative_to(canonical_root):
            raise ValueError('Package path escapes its root')
        # One no-follow metadata observation supplies both type and size.
        # Separate is_symlink/is_file/stat calls repeat the same filesystem work
        # for every payload without making the later content read atomic.
        try:info=path.lstat()
        except FileNotFoundError:
            raise ValueError('Package '+('link' if 'link' in entry else 'file')+' changed: '+name) from None
        if 'link' in entry:
            if not stat.S_ISLNK(info.st_mode) or os.readlink(path)!=entry['link']:
                raise ValueError('Package link changed: '+name)
        elif not stat.S_ISREG(info.st_mode) or info.st_size!=entry['size']:
            raise ValueError('Package file changed: '+name)
        else:
            with path.open('rb') as stream:
                if hashlib.file_digest(stream,'sha256').hexdigest()!=entry['sha256']:
                    raise ValueError('Package digest changed: '+name)
    return manifest

