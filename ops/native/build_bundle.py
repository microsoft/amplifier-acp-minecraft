"""Build on the target OS/architecture; developer tools are build-time only."""
import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def target():
    systems = {'Windows': 'windows', 'Darwin': 'macos', 'Linux': 'linux'}
    machines = {'x86_64': 'x64', 'AMD64': 'x64', 'arm64': 'arm64', 'aarch64': 'arm64', 'ARM64': 'arm64'}
    return systems[platform.system()] + '-' + machines[platform.machine()]


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def run(argv, *, cwd=None, env=None):
    subprocess.run([str(a) for a in argv], cwd=cwd, env=env, check=True)


def fetch(spec, cache):
    path = cache / spec['url'].rsplit('/', 1)[1]
    if not path.exists():
        temporary = path.with_suffix(path.suffix + '.partial')
        try:
            with urllib.request.urlopen(spec['url'], timeout=120) as response, temporary.open('wb') as out:
                shutil.copyfileobj(response, out)
            if sha(temporary) != spec['sha256']:
                raise ValueError('Runtime archive digest mismatch')
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    if sha(path) != spec['sha256']:
        raise ValueError('Cached runtime archive digest mismatch')
    return path


def extract(archive, destination, *, single_root=True):
    destination.mkdir()
    if archive.name.endswith('.zip'):
        with zipfile.ZipFile(archive) as source:
            for entry in source.infolist():
                name = entry.filename.replace('\\', '/')
                if name.startswith('/') or ':' in name or '..' in Path(name).parts:
                    raise ValueError('Unsafe runtime archive path')
            source.extractall(destination)
    else:
        with tarfile.open(archive) as source:
            source.extractall(destination, filter='data')
    if not single_root:
        return destination
    roots = list(destination.iterdir())
    if len(roots) != 1 or not roots[0].is_dir():
        raise ValueError('Expected one runtime archive root')
    return roots[0]


def inventory(root):
    entries = {}
    for path in sorted(root.rglob('*')):
        if '__pycache__' in path.parts or path.suffix == '.pyc':
            continue
        name = path.relative_to(root).as_posix()
        if path.is_symlink():
            if not path.resolve().is_relative_to(root.resolve()):
                raise ValueError('Bundle symlink escapes its private root')
            entries[name] = {'link': os.readlink(path)}
        elif path.is_file():
            entries[name] = {'sha256': sha(path), 'size': path.stat().st_size}
    return entries


def select_viewer_assets(app, versions):
    """Keep complete assets for the renderer's admitted versions only.

    This changes the fresh build output, never an installed dependency tree.
    Gameplay minecraft-data/protocol versions and generic viewer assets remain.
    """
    if (not isinstance(versions,list) or not versions
            or any(not isinstance(v,str) or not re.fullmatch(r'\d+\.\d+(?:\.\d+)?',v) for v in versions)):
        raise ValueError('Explicit screenshot versions required')
    public=app/'node_modules/prismarine-viewer/public'
    required=[public/'textures'/v for v in versions]
    required += [public/f'textures/{v}.png' for v in versions]
    required += [public/f'blocksStates/{v}.json' for v in versions]
    if any(p.is_symlink() or not p.exists() for p in required):
        raise ValueError('Complete admitted screenshot assets are required')
    removed=0
    for directory in ('textures','blocksStates'):
        for path in (public/directory).iterdir():
            version=path.name if path.is_dir() else path.stem
            if re.fullmatch(r'\d+\.\d+(?:\.\d+)?',version) and version not in versions:
                if path.is_symlink():raise ValueError('Unexpected viewer asset link')
                removed+=1
                if path.is_dir():shutil.rmtree(path)
                else:path.unlink()
    return {'versions':versions,'removed_version_entries':removed}


def build(output, cache, *, browser=True, native_shared=None, native_driver=None, native_library=None):
    if bool(native_shared) != bool(native_driver):
        raise ValueError('Shared source and exact native driver must be supplied together')
    if native_shared and not native_library:
        raise ValueError('Exact shared caller-process library is required with the driver')
    lock = json.loads((ROOT/'ops/native/runtime-lock.json').read_text())
    selected = target()
    spec = lock['targets'][selected]
    if output.exists():
        raise ValueError('Output must be a new directory')
    cache.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True)
    try:
        with tempfile.TemporaryDirectory(prefix='minecraft-native-build-') as temporary:
            scratch = Path(temporary)
            for kind in ('python', 'node'):
                extracted = extract(fetch(spec[kind], cache), scratch/kind)
                shutil.copytree(extracted, output/kind, symlinks=True)
            helper_root=extract(fetch(spec['task_helper'],cache),scratch/'task-helper',single_root=False)
            helper_name='agent-runtime.exe' if selected.startswith('windows-') else 'agent-runtime'
            helper=helper_root/helper_name
            if helper.is_symlink() or not helper.is_file() or sha(helper)!=spec['task_helper']['binary_sha256']:
                raise ValueError('Pure task-helper executable digest mismatch')
            (output/'task-helper').mkdir()
            for name in (helper_name,'LICENSE','PACKAGE.json'):
                shutil.copy2(helper_root/name,output/'task-helper'/name)

        windows = selected.startswith('windows-')
        python = output/'python'/('python.exe' if windows else 'bin/python3')
        node = output/'node'/('node.exe' if windows else 'bin/node')
        npm = output/'node'/('node_modules/npm/bin/npm-cli.js' if windows else 'lib/node_modules/npm/bin/npm-cli.js')
        if not python.is_file() or not node.is_file() or not npm.is_file():
            raise ValueError('Private runtime layout differs from the pinned archive')
        env = {**os.environ, 'PATH': str(node.parent)+os.pathsep+os.environ.get('PATH',''),
               'PYTHONDONTWRITEBYTECODE':'1', 'PYTHONNOUSERSITE':'1',
               'PLAYWRIGHT_BROWSERS_PATH':str(output/'browsers')}
        app = output/'app'; app.mkdir()
        tracked = subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
        for name in filter(None, tracked):
            if name.startswith(('.github/', 'tests/')):
                continue
            path=app/name; path.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(ROOT/name,path)
        run([python,'-m','pip','install','--disable-pip-version-check','--no-compile','--constraint',app/'ops/native/python-constraints.txt','-r',app/'requirements.txt'],env=env)
        direct = subprocess.check_output([str(python),'-c',
            "import importlib.metadata as m;print(m.distribution('agent-client-protocol').read_text('direct_url.json'))"],env=env).decode()
        sdk = json.loads(direct)
        if sdk.get('vcs_info',{}).get('commit_id') != lock['sdk_commit']:
            raise ValueError('Official SDK immutable revision differs')
        run([node,npm,'ci','--ignore-scripts','--no-audit','--no-fund'],cwd=app,env=env)
        run([node,app/'screenshot-ui/build.cjs'],cwd=app,env=env)
        versions=json.loads((app/'screenshot-ui/versions.json').read_bytes())
        mapped=json.loads(subprocess.check_output([str(node),'-e',
            "const v=require('./screenshot-ui/versions.json'),m=require('prismarine-viewer/viewer/lib/version');process.stdout.write(JSON.stringify(v.map(x=>m.getVersion(x))))"],cwd=app,env=env))
        if mapped!=versions:raise ValueError('Viewer remaps an admitted screenshot version')
        screenshot_assets=select_viewer_assets(app,versions)
        if browser:
            run([node,app/'node_modules/playwright/cli.js','install','chromium'],env=env)
        # Retain exact dependency versions and upstream provenance, not a claim
        # that equal package version strings imply equal SDK implementations.
        shared = None
        if native_shared:
            shared_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=native_shared,text=True).strip()
            if shared_revision!=json.loads((ROOT/'ops/native/shared-driver-lock.json').read_text())['commit']:
                raise ValueError('Shared driver source differs from reviewed native lock')
            if subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=native_shared).strip():
                raise ValueError('Shared source has uncommitted changes')
            library=native_shared/'support/python/constellation_native'
            site=Path(subprocess.check_output([str(python),'-I','-c','import sysconfig;print(sysconfig.get_path("purelib"))'],text=True).strip())
            if not site.resolve().is_relative_to((output/'python').resolve()):
                raise ValueError('Private native Python package directory escaped bundle')
            shutil.copytree(library,site/'constellation_native',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
            (output/'native').mkdir()
            name='constellation-native-driver.exe' if windows else 'constellation-native-driver'
            shutil.copy2(native_driver,output/'native'/name)
            library_name={'Windows':'constellation_native_driver.dll','Darwin':'libconstellation_native_driver.dylib','Linux':'libconstellation_native_driver.so'}[platform.system()]
            shutil.copy2(native_library,output/'native'/library_name)
            shared={'abi':1,'library':'native/'+library_name,'library_sha256':sha(output/'native'/library_name),'repository':'microsoft/amplifier-constellation','source':shared_revision,
                    'driver':'native/'+name,'driver_sha256':sha(output/'native'/name)}
        packages = subprocess.check_output([str(python),'-m','pip','list','--format=json'],env=env)
        (output/'python-packages.json').write_bytes(packages)
        shutil.copy2(ROOT/'ops/native/launch.py',output/'launch.py')
        (output/'minecraft.cmd').write_text('@echo off\r\n"%~dp0python\\python.exe" -I "%~dp0launch.py" %*\r\n',newline='')
        launcher=output/'minecraft';launcher.write_text('#!/bin/sh\nHERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\nexec "$HERE/python/bin/python3" -I "$HERE/launch.py" "$@"\n');launcher.chmod(0o755)
        manifest={'schema':1,'target':selected,'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip(),
                  'source_clean':not bool(subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=ROOT).strip()),
                  'runtimes':spec,'node_version':lock['node_version'],'python_version':lock['python_version'],
                  'sdk':sdk,'sdk_commit':lock['sdk_commit'],'browser_included':browser,'task_helper_version':lock['task_helper_version'],'task_helper_source':lock['task_helper_source'],
                  'screenshot_assets':screenshot_assets,
                  'commands':{'python':python.relative_to(output).as_posix(),'node':node.relative_to(output).as_posix(),'task_helper':'task-helper/'+helper_name},
                  'files':inventory(output)}
        if shared:
            manifest['native_platform']=shared
            manifest['commands']['native_driver']=shared['driver']
            manifest['commands']['native_library']=shared['library']
        (output/'manifest.json').write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n')
        run([python,'-I',output/'launch.py','doctor'],env=env)
        return manifest
    except BaseException:
        shutil.rmtree(output)
        raise


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--cache',type=Path,required=True)
    parser.add_argument('--without-browser',action='store_true',help='Explicitly incomplete developer bundle only')
    parser.add_argument('--native-shared',type=Path)
    parser.add_argument('--native-driver',type=Path)
    parser.add_argument('--native-library',type=Path)
    args=parser.parse_args()
    build(args.output.resolve(),args.cache.resolve(),browser=not args.without_browser,native_shared=args.native_shared.resolve() if args.native_shared else None,native_driver=args.native_driver.resolve() if args.native_driver else None,native_library=args.native_library.resolve() if args.native_library else None)
