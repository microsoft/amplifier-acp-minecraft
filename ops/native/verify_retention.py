"""Actual packaged Retention/NativeIO with disposable trees and the enrolled driver."""
from pathlib import Path
import argparse,hashlib,json,os,sys,tempfile,time,uuid
from unittest.mock import patch
parser=argparse.ArgumentParser()
for name in ('bundle','driver','receipt'):parser.add_argument('--'+name,type=Path,required=True)
args=parser.parse_args();bundle=args.bundle.resolve()
sys.path.insert(0,str(bundle/'app'))
manifest=json.loads((bundle/'manifest.json').read_text())
from constellation_native import initialize_root,initialize_config,NativeSession,Refused
from installation_native import NativeIO
from installation_guard import owner_io,installation_lock,read
from installation_retention import Retention
from installation_source_provider import fingerprint
import shutil

class TrackedSession(NativeSession):
 calls=[]
 def tree_remove(self,*args,**kwargs):
  self.calls.append({'timeout':kwargs.get('timeout'),'synchronous':True})
  result=super().tree_remove(*args,**kwargs)
  return result

def main():
 driver=args.driver.resolve();library=bundle/manifest['commands']['native_library']; checks=[]
 with tempfile.TemporaryDirectory(prefix='minecraft-native-retention-') as temp:
  base=Path(temp).resolve();home=base/'home';state=base/'state';shared=base/'shared';plans=shared/'plans'
  for p in [home,state,shared,plans,state/'stages',state/'backups',home/'app',home/'venv']:
   initialize_root(driver,p)
  protected=home/'original-session-fixture.json';protected.write_text('{"session":"retained-fixture","task":"unchanged","unknown":["preserve"]}')
  original=protected.read_bytes()
  # Synthetic shared-plan input belongs to this fixture, not an enrolled
  # domain write. Production retention journals below use NativeIO.
  (shared/'state.json').write_text(json.dumps({'state':'checking','transaction':None}),encoding='utf-8')
  cfg={'home':str(home),'state':str(state),'shared_plans':str(plans),'app':str(home/'app'),'venv':str(home/'venv'),
       'native_platform':{'version':1,'library':str(library),'regenerable_tree_removal':1}}
  owner={'version':1,'roots':{'home':str(home),'state':str(state)},'locks':{'installation':str(state/'installation.lock')},
         'regenerable_trees':{n:{'root':'state','path':n,'lock':'installation'} for n in ('stages','backups')}}
  conf=state/'driver.json';initialize_config(driver,conf,owner)
  keep=Retention(cfg); outside=base/'outside';outside.mkdir();sentinel=outside/'untouched';sentinel.write_text('outside')
  stage_id=str(uuid.uuid4()); retained_id=str(uuid.uuid4()); current_id=str(uuid.uuid4())
  with TrackedSession(library,driver,conf) as session,owner_io(NativeIO(cfg,session,cleanup_deadline=time.monotonic()+600)),installation_lock(state/'installation.lock'):
   assert session.describe()['regenerable_tree_removal']==1
   with patch.object(shutil.rmtree,'avoids_symlink_attacks',False):
    assert keep.safe_path('stage',stage_id)==state/'stages'/stage_id
   for ident in [stage_id,retained_id,current_id]:
    session.private_dir('state','stages/'+ident)
    session.private_dir('state','stages/'+ident+'/app')
    session.private_dir('state','stages/'+ident+'/venv')
    keep.mark('stage',ident,state='failed',created_at=time.time()-172800)
   path=state/'stages'/stage_id;(path/'partial').write_bytes(b'regenerable')
   # Windows reparse traversal is separately qualified by the shared driver.
   if os.name!='nt':(path/'outside-link').symlink_to(outside,target_is_directory=True)
   with patch.object(shutil.rmtree,'avoids_symlink_attacks',False):keep.safe_path('stage',stage_id)
   checks.append('actual rooted inspection permits absent allocation and existing reuse without Python tree-deletion guard')
   folder=plans/str(uuid.uuid4());folder.mkdir()
   (folder/'minecraft.provider.json').write_text(json.dumps({'id':folder.name,'component':'minecraft','plan':{'available':True,'stage':str(state/'stages'/retained_id)}}))
   cfg['app']=str(state/'stages'/current_id/'app')
   start=time.monotonic();result=keep.prune(fingerprint,failed=stage_id);elapsed=time.monotonic()-start
   assert result=={'pruned':['stage/'+stage_id]},result
   record=keep.owned('stage',stage_id);assert record['state']=='pruned' and record['expected_tree'] is not None
   assert not path.exists() and sentinel.read_text()=='outside'
   assert TrackedSession.calls==[{'timeout':None,'synchronous':True}],TrackedSession.calls
   checks.append('actual driver removes one unreferenced failed stage after durable expected identity; outside link target preserved')
   assert (state/'stages'/retained_id).exists() and (state/'stages'/current_id).exists()
   checks.append('retained shared plan and current app stage protected')
   # A legacy scope-less intent remains unresolved, including observed absence.
   keep.mark('stage',stage_id,state='pruning',tree_observation=None)
   assert session.tree_inspect('stages',stage_id) is None
   assert 'held' in keep.prune(fingerprint)
   checks.append('absent uncertain pruning record blocks collection; no automatic replay or false recovery')
  with NativeSession(library,driver,conf) as session:
   expected=session.tree_inspect('stages',retained_id)
   try:session.tree_remove('stages',retained_id,expected)
   except Refused:pass
   else:raise AssertionError('removal without same Session lock succeeded')
   checks.append('actual driver refuses deletion without installation lock')
  assert protected.read_bytes()==original
  checks.append('original fixture session/task/unknown bytes unchanged; no services or ACP calls')
  result={'scope':'actual packaged Minecraft Retention/NativeIO plus native driver; disposable trees only','platform':sys.platform,'target':manifest['target'],'minecraft_source':manifest['source_commit'],'driver_sha256':hashlib.sha256(driver.read_bytes()).hexdigest(),
          'shared_source':manifest['native_platform']['source'],'checks':checks,'cleanup_seconds':elapsed,'actual_cleanup_calls':TrackedSession.calls,
          'no_model_session_or_service_calls':True,'descendant_link_case':os.name!='nt','not_claimed':['60000-entry scale qualification','production cleanup','root-bound lost-reply reconciliation']}
 args.receipt.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
