"""Qualify newly built release bytes with the accepted actual ABI fixtures."""
import argparse,hashlib,json,os,sys,unittest
from pathlib import Path
p=argparse.ArgumentParser()
for n in ('bundle','shared','instance','receipt'):p.add_argument('--'+n,type=Path,required=True)
a=p.parse_args();bundle=a.bundle.resolve();shared=a.shared.resolve()
import constellation_native
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
suite=unittest.defaultTestLoader.discover(str(shared/'tests/native_python'),pattern='test_inprocess*.py')
r=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(suite)
required=('test_actual_library_abi_and_named_operations','test_helper_death_does_not_release_python_owned_lock',
 'test_actual_worker_lock_blocks_native_then_releases_same_file','test_native_lock_blocks_actual_worker_before_domain_dispatch')
missing=[name for name in required if not any(x.endswith('.'+name) for x in r.passed)]
receipt={'target':manifest['target'],'source':manifest['source_commit'],'shared':manifest['native_platform']['source'],
 'driver_sha256':manifest['native_platform']['driver_sha256'],'library_sha256':manifest['native_platform']['library_sha256'],
 'profile':'release','tests':r.testsRun,'passed':r.passed,'skipped':[(t.id(),reason) for t,reason in r.skipped],
 'missing_required':missing,'success':r.wasSuccessful() and not missing,'scope':'actual accepted ABI/fork/Worker/capability cases against new packaged release bytes'}
a.receipt.write_text(json.dumps(receipt,indent=2)+'\n')
raise SystemExit(0 if receipt['success'] else 1)
