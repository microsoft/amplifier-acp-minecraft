"""Domain journal tests; actual pointer/OS exchange is covered on six runners."""
import copy
import tempfile
import unittest
import uuid
from pathlib import Path
from installation_guard import ContinuityError,digest,durable_write,read
from installation_native_exchange import NativeExchange
from test_native_service_evidence import service


class Driver:
    def __init__(self):
        self.values={};self.calls=[];self.fail=None
        for key in ('app','venv'):
            self.values[(key,None)]={'kind':'directory','identity':key+'-original'}
            self.values[(key,'stage/'+key)]={'kind':'directory','identity':key+'-candidate'}
    def private_dir(self,*args):pass
    def exchange_inspect(self,key,entry=None):return copy.deepcopy(self.values.get((key,entry['path'] if entry else None)))
    def exchange_prepare_pointer(self,key,prepared,target,expected):
        self.calls.append(('prepare',key));v={'kind':'pointer','identity':key+'-pointer','target_identity':expected['identity']}
        self.values[(key,prepared['path'])]=v
        if self.fail=='prepare':self.fail=None;raise RuntimeError('lost preparation acknowledgment')
        return copy.deepcopy(v)
    def exchange_apply(self,key,incoming,retained,before,after):
        self.calls.append(('apply',key))
        if self.fail=='before':self.fail=None;raise RuntimeError('unknown dispatch')
        self.values[(key,retained['path'])]=self.values.pop((key,None))
        if self.fail=='gap':self.fail=None;raise RuntimeError('first rename only')
        self.values[(key,None)]=self.values.pop((key,incoming['path']))
        if self.fail=='after':self.fail=None;raise RuntimeError('lost terminal acknowledgment')


class Backend:
    def services(self):return {k:service(active=False) for k in ('body','controller')}


class NativeExchangeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);home=self.root/'home';state=self.root/'state';home.mkdir();state.mkdir()
        self.cfg={'home':str(home),'state':str(state),'native_platform':{'config':str(self.root/'driver.json')}}
        exchanges={k:{'lock':'installation','profile':{'current':str(home/k),'roots':{'state':str(state)}}} for k in ('app','venv')}
        durable_write(self.root/'driver.json',{'exchanges':exchanges})
        self.tx=str(uuid.uuid4());self.op=str(uuid.uuid4());self.driver=Driver()
        self.targets={k:{'root':'state','path':'stage/'+k} for k in ('app','venv')}
        durable_write(home/'installation-updates/gate.json',{'version':1,'transaction_id':self.tx,'closed':True})
        durable_write(state/'transactions'/(self.tx+'.json'),{'config_hash':digest(self.cfg),'phase':'ready','game':True})
    def exchange(self):return NativeExchange(self.cfg,self.driver,Backend(),self.tx,self.op,self.targets)
    def test_apply_and_explicit_rollback_keep_baseline_and_no_repeat_effect(self):
        x=self.exchange();self.assertTrue(x.apply()['applied']);calls=copy.deepcopy(self.driver.calls)
        self.assertTrue(self.exchange().apply()['applied']);self.assertEqual(self.driver.calls,calls)
        self.assertTrue(self.exchange().rollback()['rolled_back']);calls=copy.deepcopy(self.driver.calls)
        self.assertTrue(self.exchange().rollback()['rolled_back']);self.assertEqual(self.driver.calls,calls)
        for key in ('app','venv'):self.assertEqual(self.driver.values[(key,None)]['identity'],key+'-original')
        with self.assertRaises(ContinuityError):self.exchange().apply()
    def test_lost_terminal_ack_is_observed_without_a_second_exchange(self):
        self.driver.fail='after'
        with self.assertRaises(RuntimeError):self.exchange().apply()
        self.assertTrue(self.exchange().apply()['applied'])
        self.assertEqual(self.driver.calls.count(('apply','app')),1)
    def test_lost_prepare_ack_is_observed_without_recreation(self):
        self.driver.fail='prepare'
        with self.assertRaises(RuntimeError):self.exchange().apply()
        self.assertTrue(self.exchange().apply()['applied'])
        self.assertEqual(self.driver.calls.count(('prepare','app')),1)
    def test_unknown_before_or_between_renames_is_never_automatically_replayed(self):
        for failure in ('before','gap'):
            with self.subTest(failure=failure):
                self.op=str(uuid.uuid4());self.driver=Driver();self.driver.fail=failure
                with self.assertRaises(RuntimeError):self.exchange().apply()
                calls=copy.deepcopy(self.driver.calls)
                with self.assertRaises(ContinuityError):self.exchange().apply()
                self.assertEqual(self.driver.calls,calls)
    def test_different_target_or_open_gate_refuses_before_effect(self):
        self.exchange().apply();self.targets['app']['path']='other/app'
        with self.assertRaises(ContinuityError):self.exchange()
        self.targets['app']['path']='stage/app';calls=copy.deepcopy(self.driver.calls)
        durable_write(Path(self.cfg['home'])/'installation-updates/gate.json',{'closed':False})
        with self.assertRaises(ContinuityError):self.exchange().rollback()
        self.assertEqual(self.driver.calls,calls)

if __name__=='__main__':unittest.main()
