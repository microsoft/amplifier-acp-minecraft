"""Disposable packaged fresh setup and complete archive staging; no game or ACP.

The archive route/metadata is a fixed local fixture; production stage_package
still validates, copies and extracts every byte, checks SDK and browser, and
writes its actual receipt. No public-release claim follows from this fixture.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

parser=argparse.ArgumentParser()
for name in ('bundle','source','shared','archive','receipt'):parser.add_argument('--'+name,type=Path,required=True)
parser.add_argument('--child-root',type=Path)
args=parser.parse_args();bundle=args.bundle.resolve();source=args.source.resolve();shared=args.shared.resolve()
sys.path[:0]=[str(bundle/'app'),str(shared/'tests/native_python')]
if args.child_root is None:
 # The ABI retains loaded libraries for process lifetime (fork hooks). Reap the
 # actual caller before removing its private library on Windows.
 from test_driver import protect
 base=Path(tempfile.mkdtemp(prefix='minecraft-packaged-setup-')).resolve();protect(base)
 result=subprocess.run([sys.executable,'-I',str(Path(__file__).resolve()),*sys.argv[1:],'--child-root',str(base)])
 if args.receipt.exists():
  receipt=json.loads(args.receipt.read_bytes())
  if not receipt.get('cleanup_errors'):
   shutil.rmtree(base);receipt['disposable_removed']=True
  else:receipt['retained_disposable_root']=str(base)
  args.receipt.write_text(json.dumps(receipt,indent=2)+'\n')
 else:print('Retained unqualified fixture root:',base,file=sys.stderr)
 raise SystemExit(result.returncode)
from constellation_native import NativeSession
from installation_native_bootstrap import setup
from installation_native import native_scope
from installation_guard import installation_lock,service_stopped
from installation_native_package import stage_package
from installation_source_provider import Provider
from test_service import NativeServiceApplicationTests

manifest=json.loads((bundle/'manifest.json').read_bytes())
archive=args.archive.resolve();digest=hashlib.sha256(archive.read_bytes()).hexdigest()
report={'scope':'disposable actual packaged fresh setup/no-start services and full local archive staging',
 'source':manifest['source_commit'],'target':manifest['target'],'archive_sha256':digest,
 'public_release':False,'model_calls':0,'world_calls':0,'source_fixture':str(source)}
class Cleanup(NativeServiceApplicationTests):
 def receipt_identities(self,receipt):return [] # Fresh setup never starts.

base=args.child_root.resolve();root=base/'installation'
cleanup_ok=False;registered={}
try:
 plan={'schema':1,'root':str(root),'game':{'control_port':1234,'token':'disposable-no-server','screenshots':{'enabled':True}},
       'endpoint':{'command':[sys.executable,'-I',str(source/'tests/session_probe_fixture.py')],'cwd':str(base)}}
 start=time.monotonic();result=setup(bundle,plan);report['setup_seconds']=time.monotonic()-start
 cfg=json.loads(Path(result['owner_config']).read_bytes());receipt=json.loads(Path(result['receipt']).read_bytes())
 report['setup']=result;registered=receipt['services']
 assert receipt['phase']=='registered_stopped' and not (root/'home/session.json').exists()
 assert all(v['phase']=='registered_stopped' and v['creation']['created'] is True for v in registered.values())
 before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'home').iterdir() if p.is_file()}
 try:setup(bundle,plan)
 except Exception as error:
  assert 'never reuses' in str(error);report['repeat_refused_without_retry']=True
 else:raise AssertionError('Setup reused a completed home')
 provider=Provider(cfg)
 tag='fixture-'+manifest['source_commit'];name='minecraft-'+manifest['target']+'.tar.gz'
 url='https://github.com/microsoft/amplifier-acp-minecraft/releases/download/'+tag+'/'+name
 release={'tag_name':tag,'assets':[{'name':name,'digest':'sha256:'+digest,'size':archive.stat().st_size,'browser_download_url':url}]}
 def gh(route):
  if route=='releases/latest':return release
  if route=='commits/'+tag:return {'sha':manifest['source_commit']}
  if route.startswith('compare/'):return {'status':'identical'}
  raise AssertionError('Unexpected fixture metadata request: '+route)
 def download(route,**kw):
  assert route==url
  return archive.open('rb')
 stage=root/'state/stages/00000000-0000-4000-8000-000000000001'
 started=time.monotonic()
 with native_scope(cfg,cleanup_deadline=started+600),installation_lock(root/'state/installation.lock'),\
      patch.object(provider,'gh',side_effect=gh),patch('installation_native_package.urllib.request.urlopen',side_effect=download),\
      patch.dict(os.environ,{'PLAYWRIGHT_BROWSERS_PATH':str(bundle/'browsers')}):
  sdk=stage_package(provider,manifest['source_commit'],manifest['source_commit'],stage)
 elapsed=time.monotonic()-started
 report['full_archive_staging']={'seconds':elapsed,'fits_provider_600':elapsed<600,'sdk':sdk,
      'receipt':json.loads((stage/'package-receipt.json').read_bytes()),'local_metadata_and_download_fixture':True}
 assert elapsed<600,'Actual staging exceeds existing provider budget'
 assert {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'home').iterdir() if p.is_file()}==before
 with native_scope(cfg) as native:
  for role in ('body','controller'):assert service_stopped(native.service_snapshot(role))
 report['no_start_and_home_continuity']=True;report['passed']=True
finally:
 errors=[]
 # Only names returned by this unique fresh setup may be removed. Never clean
 # an unproved registration, unrelated task, or existing home on failure.
 journal=root/'state/setup.json'
 if journal.exists():registered=json.loads(journal.read_bytes()).get('services',{})
 for role,value in registered.items():
  if value.get('phase')!='registered_stopped' or value.get('creation',{}).get('created') is not True:
   errors.append('Uncertain registration retained: '+role);continue
  profile=value['profile'];name=profile['name']
  if not re.fullmatch(r'minecraft-[0-9a-f-]{36}-(body|controller)(\.service)?',name):
   errors.append('Unexpected fixture name');continue
  try:
   if sys.platform=='win32':
    # Test-only removal of this stopped, fresh GUID task using the native OS
    # utility. No PowerShell policy change and no product OS-control fork.
    subprocess.run([str(Path(os.environ['SystemRoot'])/'System32/schtasks.exe'),'/Delete','/TN',name,'/F'],check=True,capture_output=True,timeout=30)
   else:
    Cleanup().cleanup(name,Path(profile['definition_path']),root/'state/native.json',root/'state'/(role+'-identity.json'))
  except Exception as error:errors.append(repr(error))
 report['cleanup_errors']=errors
 if not errors:report['parent_cleanup_after_caller_exit']=True
 else:report['retained_disposable_root']=str(root)
 report['disposable_removed']=cleanup_ok
 args.receipt.write_text(json.dumps(report,indent=2)+'\n')
 if errors:raise RuntimeError('Disposable cleanup incomplete; see receipt')
print(json.dumps({'passed':report.get('passed',False),'setup_seconds':report.get('setup_seconds'),
                  'staging_seconds':report.get('full_archive_staging',{}).get('seconds')}))
