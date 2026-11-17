import types
import unittest
from setup_observation import SetupObservation


class ObservationTests(unittest.TestCase):
    def test_same_native_call_result_arguments_and_exception_once(self):
        marker=object();failure=RuntimeError('original uncertainty');calls=[]
        class Session:
            def _call(self,op,**fields):
                calls.append((self,op,fields))
                if op=='fail':raise failure
                return marker
        original=Session._call;session=Session();observer=SetupObservation()
        with observer.native_calls(Session):
            self.assertIs(session._call('write',mutating=True,payload=marker),marker)
            observer.phase='stage'
            with self.assertRaises(RuntimeError) as raised:session._call('fail',timeout=30)
            self.assertIs(raised.exception,failure)
        self.assertIs(Session._call,original)
        self.assertEqual(calls,[(session,'write',{'mutating':True,'payload':marker}),(session,'fail',{'timeout':30})])
        self.assertEqual(observer.records['setup']['native:write']['calls'],1)
        self.assertEqual(observer.records['stage']['native:fail']['errors'],1)

    def test_interrupt_is_not_suppressed_or_repeated(self):
        calls=[];failure=KeyboardInterrupt()
        def operation():calls.append(1);raise failure
        observer=SetupObservation()
        with self.assertRaises(KeyboardInterrupt) as raised:observer.invoke('original',operation)
        self.assertIs(raised.exception,failure);self.assertEqual(calls,[1])
        self.assertEqual(observer.records['setup']['original']['errors'],1)

    def test_function_restored_and_nested_times_not_used_as_deadlines(self):
        calls=[];marker=object();module=types.SimpleNamespace(run=lambda *a,**kw:(calls.append((a,kw)),marker)[1])
        original=module.run;observer=SetupObservation()
        with observer.function(module,'run','payload'):
            self.assertIs(module.run(marker,deadline=123),marker)
        self.assertIs(module.run,original);self.assertEqual(calls,[((marker,),{'deadline':123})])
        self.assertEqual(observer.records['setup']['payload']['calls'],1)


if __name__=='__main__':unittest.main()
