"""Disposable CI fixture preparation, never a production installation helper.

The shared driver remains the authority for validating protected configuration.
The Windows fixture must establish both its DACL and current-user ownership:
a private DACL alone does not change an inherited Administrators owner.
"""
import json
from pathlib import Path
import re
import subprocess


def protect_fixture_path(path, root, shared_protect, *, windows=False,
                         user_sid=None, run=subprocess.run):
    path, root = Path(path), Path(root)
    if (not root.is_absolute() or root.resolve(strict=True) != root
            or not path.is_absolute() or path.resolve(strict=True) != path
            or not path.is_relative_to(root) or path.is_symlink()
            or (hasattr(path, 'is_junction') and path.is_junction())):
        raise ValueError('Fixture protection requires an existing path inside its fresh root')
    if windows and (not isinstance(user_sid, str)
                    or re.fullmatch(r'S-1-(?:\d+-)*\d+', user_sid) is None):
        raise ValueError('Fixture requires the actual current-user SID')
    shared_protect(path)
    if windows:
        # Fixed test-only argv; no recursion, ACL broadening, shell or elevation.
        # Numeric SID prefix and /setowner are documented by Microsoft icacls.
        run(['icacls.exe', str(path), '/setowner', '*'+user_sid, '/L', '/Q'],
            capture_output=True, text=True, timeout=10, check=True)


def fixture_application_identities(receipt, service):
    """Read only this disposable role's generation-bound application receipt."""
    if service not in ('body','controller'):
        raise ValueError('Unexpected disposable Minecraft service role')
    if not receipt.exists():return []
    value=json.loads(receipt.read_text())
    if value.get('schema')!=1 or value.get('service')!=service:
        raise ValueError('Unrecognized disposable application receipt')
    return [value[key] for key in ('supervisor','application')]
