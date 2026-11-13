"""Disposable CI fixture preparation, never a production installation helper.

The shared driver remains the authority for validating protected configuration.
The qualified shared fixture helper owns platform permissions and ownership.
Minecraft only restricts its use to paths within this fresh disposable root.
"""
import json
import hashlib
from pathlib import Path


def copy_fixture_driver(source, state, config):
    """Allocate one private input in this new fixture; no helper lease claimed."""
    from constellation_native import Session
    from installation_native_package import fill_created_payload_file
    source,state=Path(source),Path(state)
    destination=state/('fixture-driver'+source.suffix)
    with Session(source,config) as initial:
        initial.private_write('state',destination.name,b'',create_only=True)
    with source.open('rb') as stream:fill_created_payload_file(destination,stream,0o700)
    if hashlib.sha256(destination.read_bytes()).digest()!=hashlib.sha256(source.read_bytes()).digest():
        raise ValueError('Disposable driver copy changed')
    return destination


def protect_fixture_path(path, root, shared_protect):
    path, root = Path(path), Path(root)
    if (not root.is_absolute() or root.resolve(strict=True) != root
            or not path.is_absolute() or path.resolve(strict=True) != path
            or not path.is_relative_to(root) or path.is_symlink()
            or (hasattr(path, 'is_junction') and path.is_junction())):
        raise ValueError('Fixture protection requires an existing path inside its fresh root')
    shared_protect(path)


def fixture_application_identities(receipt, service):
    """Read only this disposable role's generation-bound application receipt."""
    if service not in ('body','controller'):
        raise ValueError('Unexpected disposable Minecraft service role')
    if not receipt.exists():return []
    value=json.loads(receipt.read_text())
    if value.get('schema')!=1 or value.get('service')!=service:
        raise ValueError('Unrecognized disposable application receipt')
    return [value[key] for key in ('supervisor','application')]
