"""Qualify newly built release bytes with the accepted actual ABI fixtures."""
import argparse,contextlib,hashlib,json,os,sys,unittest
from pathlib import Path
p=argparse.ArgumentParser()
for n in ('bundle','shared','instance','receipt'):p.add_argument('--'+n,type=Path,required=True)
a=p.parse_args();bundle=a.bundle.resolve();shared=a.shared.resolve()
import constellation_native
# -I deliberately excludes this script's directory; this is a fixed local
# qualification helper, never a package or agent-selected import path.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from boundary_fixture_overlay import prepare
manifest=json.loads((bundle/'manifest.json').read_bytes())
facade=Path(constellation_native.__file__).parent
for name in ('__init__.py','client.py','inprocess.py'):
 assert (facade/name).read_bytes()==(shared/'support/python/constellation_native'/name).read_bytes(),name
os.environ.update(CONSTELLATION_NATIVE_DRIVER=str(bundle/manifest['commands']['native_driver']),
 CONSTELLATION_NATIVE_LIBRARY=str(bundle/manifest['commands']['native_library']),
 CONSTELLATION_NATIVE_LIBRARY_SHA256=manifest['native_platform']['library_sha256'],
 CONSTELLATION_INSTANCE_SOURCE=str(a.instance.resolve()),NATIVE_TEST_PYTHON=sys.executable)
class Result(unittest.TextTestResult):
 def __init__(self,*args,**kwargs):super().__init__(*args,**kwargs);self.passed=[]
 def addSuccess(self,test):super().addSuccess(test);self.passed.append(test.id())
fixture_tests,fixture_provenance=prepare(shared,Path('qualification-fixtures/native-boundary').resolve())
suite=unittest.defaultTestLoader.discover(str(fixture_tests),pattern='test_inprocess*.py')
suite.addTests(unittest.defaultTestLoader.discover(str(fixture_tests),pattern='test_fixture_close_evidence.py'))
class Tee:
 def __init__(self,*streams):self.streams=streams
 def write(self,value):
  for stream in self.streams:stream.write(value)
  return len(value)
 def flush(self):
  for stream in self.streams:stream.flush()
cleanup_log=a.receipt.with_suffix('.cleanup.log')
with cleanup_log.open('w',encoding='utf-8') as log,contextlib.redirect_stderr(Tee(sys.stderr,log)):
 r=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(suite)
required=('test_actual_library_abi_and_named_operations','test_helper_death_does_not_release_python_owned_lock',
 'test_actual_worker_lock_blocks_native_then_releases_same_file','test_native_lock_blocks_actual_worker_before_domain_dispatch')
missing=[name for name in required if not any(x.endswith('.'+name) for x in r.passed)]
receipt={'target':manifest['target'],'source':manifest['source_commit'],'shared':manifest['native_platform']['source'],
 'fixture_overlay':fixture_provenance,'cleanup_observations':{'path':str(cleanup_log),'sha256':hashlib.sha256(cleanup_log.read_bytes()).hexdigest()},
 'historical_shared_worker_fixture':json.loads((shared/'tests/native_python/fixtures/worker_source.json').read_bytes()),
 'driver_sha256':manifest['native_platform']['driver_sha256'],'library_sha256':manifest['native_platform']['library_sha256'],
 'profile':'release','tests':r.testsRun,'passed':r.passed,'skipped':[(t.id(),reason) for t,reason in r.skipped],
 'missing_required':missing,'success':r.wasSuccessful() and not missing,'scope':'actual accepted ABI/fork/Worker/capability cases plus hash-bound canonical test-only cleanup observer against new packaged release bytes'}
a.receipt.write_text(json.dumps(receipt,indent=2)+'\n')
raise SystemExit(0 if receipt['success'] else 1)
