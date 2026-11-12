"""Stage a published target package; native clients do not need Git/npm/pip.

Public release bytes and their exact source tree are verified before extraction.
Changing bundled base interpreters is a separate installation migration; this
source/dependency provider never silently changes its executing helper runtime.
"""
import hashlib
import os
from pathlib import Path
import platform
import re
import tarfile
import urllib.request
from installation_guard import ContinuityError, durable_write, current_owner_io
from native_package import validate


def target():
    systems={'Linux':'linux','Darwin':'macos','Windows':'windows'}
    architectures={'x86_64':'x64','AMD64':'x64','aarch64':'arm64','arm64':'arm64','ARM64':'arm64'}
    return systems[platform.system()]+'-'+architectures[platform.machine()]


def private_directory(path):
    owner=current_owner_io()
    if owner is None or not hasattr(owner,'mkdir'):
        raise ContinuityError('Native package staging requires its protected owner storage scope')
    owner.mkdir(path)


def stage_package(provider,revision,previous,stage):
    if provider.c['channel']!='stable':
        raise ContinuityError('Native source updates require a published target package on the stable channel')
    release=provider.gh('releases/latest')
    if release.get('draft') or release.get('prerelease'):
        raise ContinuityError('Native target release is not published stable')
    tag=release.get('tag_name','')
    if not re.fullmatch('[A-Za-z0-9._-]+',tag) or provider.gh('commits/'+tag)['sha']!=revision:
        raise ContinuityError('Native release changed after candidate selection')
    comparison=provider.gh('compare/'+previous+'...'+revision)
    if comparison.get('status') not in ('ahead','identical'):
        raise ContinuityError('Native source downgrade or unrelated history is not allowed')
    name='minecraft-'+target()+'.tar.gz'
    assets=[a for a in release.get('assets',[]) if a.get('name')==name]
    if len(assets)!=1:raise ContinuityError('One exact native target package is required')
    asset=assets[0];digest=asset.get('digest','')
    if not re.fullmatch('sha256:[0-9a-f]{64}',digest):
        raise ContinuityError('Native release archive lacks its published digest')
    url='https://github.com/microsoft/amplifier-acp-minecraft/releases/download/'+tag+'/'+name
    if asset.get('browser_download_url')!=url or not 0<int(asset.get('size',0))<=2*1024**3:
        raise ContinuityError('Native release artifact route/size is invalid')
    if stage.exists():raise ContinuityError('Native build destination must be a fresh unreferenced stage')
    private_directory(stage);archive=stage/'release.tar.gz';h=hashlib.sha256();size=0
    with urllib.request.urlopen(url,timeout=120) as response,archive.open('xb') as out:
        while block:=response.read(1024*1024):
            size+=len(block)
            if size>asset['size']:raise ContinuityError('Native archive exceeded declared size')
            h.update(block);out.write(block)
    if size!=asset['size'] or h.hexdigest()!=digest[7:]:
        raise ContinuityError('Native archive differs from the published artifact')
    package=stage/'package';private_directory(package)
    with tarfile.open(archive,'r:gz') as source:
        total=0
        members=source.getmembers()
        for item in members:
            path=Path(item.name);total+=item.size
            if (path.is_absolute() or '..' in path.parts or '\\' in item.name or ':' in item.name
                    or not (item.isfile() or item.isdir() or item.issym()) or total>5*1024**3):
                raise ContinuityError('Native archive contains an unsafe entry')
        # Protected roots and directories come from the shared storage owner,
        # including on Windows. Archive extraction never establishes ACLs.
        directories=set()
        for item in members:
            path=Path(item.name)
            directories.update(p for p in path.parents if p!=Path('.'))
            if item.isdir():directories.add(path)
        for path in sorted(directories,key=lambda p:(len(p.parts),p.as_posix())):
            private_directory(package/path)
        source.extractall(package,filter='data')
    manifest=validate(package)
    if manifest.get('target')!=target() or manifest.get('source_clean') is not True:
        raise ContinuityError('Native package target or source provenance differs')
    source=manifest.get('source_commit','')
    if not re.fullmatch('[0-9a-f]{40}',source):raise ContinuityError('Native package lacks exact source')
    if source!=revision and provider.gh('git/commits/'+source)['tree']['sha']!=provider.gh('git/commits/'+revision)['tree']['sha']:
        raise ContinuityError('Published package source tree differs from selected source')
    native=manifest.get('native_platform',{})
    driver=Path(provider.c['native_platform']['driver'])
    if (native.get('repository')!='microsoft/amplifier-constellation'
            or native.get('driver_sha256')!=hashlib.sha256(driver.read_bytes()).hexdigest()):
        raise ContinuityError('Shared native driver change requires its separately reviewed installation migration')
    for key in ('python','node'):
        binary=package/manifest['commands'][key]
        if hashlib.sha256(binary.read_bytes()).hexdigest()!=hashlib.sha256(Path(provider.c[key]).read_bytes()).hexdigest():
            raise ContinuityError('Base interpreter change requires its separately reviewed native installation migration')
    relative=Path(manifest['commands']['python']).relative_to('python').as_posix()
    if relative!=provider.c['native_platform'].get('environment_python'):
        raise ContinuityError('Native private Python layout changed')
    # New, unreferenced staging names only. These are not installed pointers;
    # installed exchange/rollback is exclusively performed by the native driver.
    os.rename(package/'app',stage/'app');os.rename(package/'python',stage/'venv')
    from installation_source_provider import verify_sdk
    sdk=verify_sdk(stage/'venv',stage/'app')
    if sdk['commit']!=manifest['sdk_commit']:raise ContinuityError('Packaged official SDK provenance differs')
    provider.screenshot_browser(stage/'app')
    archive.unlink()
    durable_write(stage/'package-receipt.json',{'revision':revision,'package_source':source,
       'release':tag,'archive_sha256':digest[7:],'target':target(),
       'package_manifest_sha256':hashlib.sha256((package/'manifest.json').read_bytes()).hexdigest()})
    return sdk
