"""Fixed local entry points using only this bundle's private runtimes."""
import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent


# Package source is fixed by the downloaded release digest before installation.
sys.path.insert(0,str(ROOT/'app'))
from native_package import validate


def doctor(root):
    manifest=validate(root)
    system={'Windows':'windows','Darwin':'macos','Linux':'linux'}[platform.system()]
    arch={'AMD64':'x64','x86_64':'x64','ARM64':'arm64','arm64':'arm64','aarch64':'arm64'}[platform.machine()]
    if manifest['target']!=system+'-'+arch:
        raise ValueError('Package target does not match the native host')
    sdk=json.loads(importlib.metadata.distribution('agent-client-protocol').read_text('direct_url.json'))
    if sdk!=manifest['sdk'] or sdk.get('vcs_info',{}).get('commit_id')!=manifest['sdk_commit']:
        raise ValueError('Installed official SDK provenance differs')
    node=root/manifest['commands']['node']
    version=subprocess.check_output([str(node),'--version'],text=True).strip()
    if version!='v'+manifest['node_version'] or platform.python_version()!=manifest['python_version']:
        raise ValueError('Private runtime version differs')
    helper=root/manifest['commands']['task_helper']
    capability=json.loads(subprocess.check_output([str(helper),'helper-capabilities'],text=True,timeout=10))
    if capability.get('schema_version')!=1 or any(capability.get('helpers',{}).get(name,{}).get('version')!=2 or capability['helpers'][name].get('command')!=name+'-v2' for name in ('watch','continuation')):
        raise ValueError('Pure task-helper capability differs')
    # Import the actual production client and Node dependency graph; no sessions,
    # model prompts, Minecraft connections or user home writes are performed.
    sys.path.insert(0,str(root/'app'))
    __import__('acp_client')
    subprocess.run([str(node),'-e',"for(const n of ['mineflayer','mineflayer-pathfinder','@modelcontextprotocol/sdk/server/mcp.js','playwright'])require(n)"],cwd=root/'app',check=True)
    return {'verified':True,'target':manifest['target'],'source_commit':manifest['source_commit'],
            'sdk_commit':manifest['sdk_commit'],'browser_included':manifest['browser_included'],'task_helper':capability,
            'game_connected':False,'session_created':False}


def run_windows(argv, env):
    # Windows exec* does not provide Unix process replacement/argv semantics.
    # Use subprocess's native argument quoting, without a shell. The native
    # service owner must supervise the process tree; this is the interactive CLI.
    child=subprocess.Popen(argv, env=env)
    try:
        return child.wait()
    finally:
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill();child.wait()


def main():
    parser=argparse.ArgumentParser(description='Minecraft connector with private Node, Python and official ACP SDK')
    commands=parser.add_subparsers(dest='command',required=True)
    commands.add_parser('doctor',help='Read-only package/runtime verification')
    setup=commands.add_parser('setup',help='Prepare a fresh private home and register stopped services')
    setup.add_argument('--plan',type=Path,required=True)
    for name in ('body','controller'):
        p=commands.add_parser(name);p.add_argument('--home',type=Path,required=True)
    args=parser.parse_args()
    if args.command=='doctor':
        print(json.dumps(doctor(ROOT)));return
    if args.command=='setup':
        from installation_native_bootstrap import setup
        print(json.dumps(setup(ROOT,json.loads(args.plan.read_bytes()))));return
    manifest=validate(ROOT)
    home=args.home.expanduser().resolve()
    if not home.is_dir() or not (home/'config.json').is_file():
        raise ValueError('Use an explicitly prepared connection home; this command does not set up or authorize one')
    env={**os.environ,'PYTHONNOUSERSITE':'1','PYTHONDONTWRITEBYTECODE':'1','PLAYWRIGHT_BROWSERS_PATH':str(ROOT/'browsers')}
    if args.command=='body':
        argv=[str(ROOT/manifest['commands']['node']),str(ROOT/'app/body.cjs'),str(home/'config.json')]
    else:
        argv=[str(ROOT/manifest['commands']['python']),'-s',str(ROOT/'app/adapter.py'),'--home',str(home)]
    if os.name=='nt':
        raise SystemExit(run_windows(argv,env))
    os.execve(argv[0],argv,env)


if __name__=='__main__':
    main()
