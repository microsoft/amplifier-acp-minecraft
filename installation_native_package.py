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
import shutil
import stat
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



def create_payload_file(path, stream, mode=0o600):
    """Create ownership before streaming large immutable package contents.

    The whole caller action holds its installation lock. Staging is unpublished;
    interruption retains the partial stage, never an installed replacement.
    """
    owner=current_owner_io()
    if owner is None:raise ContinuityError('Private payload creation needs owner scope')
    name,relative=owner.relative(path)
    owner.session.private_write(name,relative,b'',create_only=True)
    before=path.stat(follow_symlinks=False)
    flags=os.O_WRONLY | getattr(os,'O_NOFOLLOW',0) | getattr(os,'O_BINARY',0)
    fd=os.open(path,flags)
    with os.fdopen(fd,'wb') as output:
        opened=os.fstat(output.fileno())
        if (not stat.S_ISREG(opened.st_mode) or opened.st_size!=0
                or (before.st_dev,before.st_ino)!=(opened.st_dev,opened.st_ino)):
            raise ContinuityError('Fresh staged file identity changed before contents')
        shutil.copyfileobj(stream,output,1024*1024)
        output.flush();os.fsync(output.fileno())
    if os.name!='nt':path.chmod(0o700 if mode & 0o111 else 0o600)


def extract_private_archive(archive,package):
    """Extract one exact inventoried archive into an empty protected directory."""
    with tarfile.open(archive,'r:gz') as source:
        members=source.getmembers();total=0;names=set();folded=set()
        for item in members:
            path=Path(item.name);total+=item.size
            if (path.is_absolute() or path==Path('.') or '..' in path.parts
                    or '\\' in item.name or ':' in item.name or item.name in names
                    or (os.name=='nt' and item.name.casefold() in folded)
                    or not (item.isfile() or item.isdir() or item.issym())
                    or total>5*1024**3):
                raise ContinuityError('Native archive contains an unsafe entry')
            names.add(item.name);folded.add(item.name.casefold())
        index=source.getmember('manifest.json')
        if not index.isfile() or index.size>32*1024**2:
            raise ContinuityError('Native archive manifest is invalid')
        manifest=__import__('json').load(source.extractfile(index))
        payload={m.name for m in members if not m.isdir()}
        if payload!=set(manifest['files'])|{'manifest.json'}:
            raise ContinuityError('Native archive contains untracked payload')
        directories=set()
        for item in members:
            path=Path(item.name)
            directories.update(p for p in path.parents if p!=Path('.'))
            if item.isdir():directories.add(path)
        link_names={Path(m.name) for m in members if m.issym()}
        if directories & link_names:
            raise ContinuityError('Native archive link cannot be a payload parent')
        for path in sorted(directories,key=lambda p:(len(p.parts),p.as_posix())):
            private_directory(package/path)
        for item in members:
            path=package/item.name
            if item.isfile():
                with source.extractfile(item) as stream:create_payload_file(path,stream,item.mode)
            elif item.issym():
                target=Path(item.linkname)
                if (target.is_absolute() or '\\' in item.linkname or ':' in item.linkname
                        or not (path.parent/target).resolve().is_relative_to(package.resolve())):
                    raise ContinuityError('Native archive link escapes package')
                os.symlink(item.linkname,path)
    return validate(package)


def copy_private_payload(bundle,prefix,destination,manifest):
    """Copy inventoried files only; no developer cache or untracked source."""
    private_directory(destination)
    selected={name[len(prefix)+1:]:entry for name,entry in manifest['files'].items()
              if name.startswith(prefix+'/')}
    if not selected:raise ContinuityError('Empty package payload selection')
    directories={p for name in selected for p in Path(name).parents if p!=Path('.')}
    for rel in sorted(directories,key=lambda p:(len(p.parts),p.as_posix())):
        private_directory(destination/rel)
    for name,entry in selected.items():
        source=bundle/prefix/name;target=destination/name
        if 'link' in entry:
            if not (target.parent/entry['link']).resolve().is_relative_to(destination.resolve()):
                raise ContinuityError('Copied runtime link escapes selected payload')
            os.symlink(entry['link'],target)
        else:
            with source.open('rb') as stream:create_payload_file(target,stream,source.stat().st_mode)
            if hashlib.sha256(target.read_bytes()).hexdigest()!=entry['sha256']:
                raise ContinuityError('Copied package content differs from manifest')


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
    extract_private_archive(archive,package)
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
    enrolled=provider.c['native_platform']
    if 'library' in enrolled:
        library=Path(enrolled['library'])
        if (native.get('abi')!=1 or native.get('library_sha256')!=enrolled.get('library_sha256')
                or hashlib.sha256(library.read_bytes()).hexdigest()!=enrolled['library_sha256']):
            raise ContinuityError('Native library change requires a separately reviewed installation migration')
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
