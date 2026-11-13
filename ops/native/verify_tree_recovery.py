"""Actual packaged journal reconciliation; only disposable fixture artifacts."""
from pathlib import Path
import argparse,sys,tempfile,json,hashlib,uuid,time
parser=argparse.ArgumentParser()
for name in ('bundle','driver','receipt'):parser.add_argument('--'+name,type=Path,required=True)
args=parser.parse_args();bundle=args.bundle.resolve()
sys.path.insert(0,str(bundle/'app'))
manifest=json.loads((bundle/'manifest.json').read_text())
from constellation_native import NativeSession,Unknown,initialize_root,initialize_config
from installation_native import NativeIO
from installation_retention import Retention
from installation_guard import owner_io,installation_lock
from installation_source_provider import fingerprint
DRIVER=args.driver.resolve()
LIBRARY=bundle/manifest['commands']['native_library']
class LostAcknowledgment(NativeSession):
 deletions=0
 def tree_remove(self,*a,**kw):
  result=super().tree_remove(*a,**kw)
  assert result=={'absent':True}
  type(self).deletions+=1
  raise self._lost('response_lost','Simulated lost reply after real committed removal',True)
results=[]
for scenario in ('same-scope','replaced-root','changed-profile','legacy-missing-scope'):
 with tempfile.TemporaryDirectory(prefix='minecraft-scoped-recovery-') as tmp:
  base=Path(tmp).resolve();home=base/'home';state=base/'state';shared=base/'shared';plans=shared/'plans'
  for p in (home,state,shared,plans,state/'stages',state/'backups',home/'app',home/'venv'):initialize_root(DRIVER,p)
  (shared/'state.json').write_text(json.dumps({'state':'succeeded','transaction':None}))
  protected=home/'session.json';protected.write_text('{"original":"unchanged"}')
  cfg={'home':str(home),'state':str(state),'app':str(home/'app'),'venv':str(home/'venv'),'shared_plans':str(plans),'native_platform':{'version':1,'library':str(LIBRARY),'regenerable_tree_removal':1}}
  # Publish inside the production-initialized owner root, not the disposable
  # harness parent (which may be Administrators-owned on Windows runners).
  conf=state/'driver.json';doc={'version':1,'roots':{'home':str(home),'state':str(state)},'locks':{'installation':str(state/'installation.lock')},'regenerable_trees':{n:{'root':'state','path':n,'lock':'installation'} for n in ('stages','backups')}}
  initialize_config(DRIVER,conf,doc);ident=str(uuid.uuid4());keep=Retention(cfg);old_count=LostAcknowledgment.deletions
  with LostAcknowledgment(LIBRARY,DRIVER,conf) as session:
   try:
    with owner_io(NativeIO(cfg,session,cleanup_deadline=time.monotonic()+600)),installation_lock(state/'installation.lock'):
     session.private_dir('state','stages/'+ident);session.private_write('state','stages/'+ident+'/partial',b'regenerable')
     keep.mark('stage',ident,state='failed',created_at=1)
     keep.prune(fingerprint,failed=ident)
   except Unknown:pass
   else:raise AssertionError('No lost acknowledgement')
  record=keep.owned('stage',ident);assert record['state']=='pruning' and record['tree_observation']['scope']
  if scenario=='replaced-root':
   (state/'stages').rename(state/'retained-original-stages');initialize_root(DRIVER,state/'stages')
  if scenario=='changed-profile':
   doc['locks']['installation']=str(state/'different-installation.lock');conf=state/'second-driver.json';initialize_config(DRIVER,conf,doc)
  with NativeSession(LIBRARY,DRIVER,conf) as session,owner_io(NativeIO(cfg,session)),installation_lock(state/'installation.lock'):
   if scenario=='legacy-missing-scope':record=keep.mark('stage',ident,tree_observation=None)
   result=keep.prune(fingerprint)
   if scenario=='same-scope':
    assert result=={'pruned':[],'reconciled':['stage/'+ident]},result
    assert keep.prune(fingerprint)=={'pruned':[]}
    for key in ('expected_tree','tree_observation','reason','pruned_at'):assert keep.owned('stage',ident)[key]==record[key]
   else:
    assert 'held' in result and keep.owned('stage',ident)==record,result
  assert LostAcknowledgment.deletions==old_count+1
  assert protected.read_text()=='{"original":"unchanged"}'
  results.append({'case':scenario,'one_actual_deletion':True,'result':result,'session_preserved':True})
args.receipt.write_text(json.dumps({'driver_sha256':hashlib.sha256(DRIVER.read_bytes()).hexdigest(),'shared':manifest['native_platform']['source'],'minecraft':manifest['source_commit'],'target':manifest['target'],'cases':results,'scope':'Actual packaged Minecraft journal with real target-native lock/removal; lost reply simulated after confirmed driver deletion; no services/ACP/model/world'},indent=2)+'\n')
print('PASS',len(results),'actual consumer cases, exactly',LostAcknowledgment.deletions,'deletions total')
