"""Test-only synchronous timing observations. Never dispatch or retry work."""
import time
from contextlib import contextmanager
from unittest.mock import patch


class SetupObservation:
    def __init__(self):
        self.phase='setup'
        self.records={}

    def invoke(self, label, operation, *args, **kwargs):
        row=self.records.setdefault(self.phase,{}).setdefault(label,
            {'calls':0,'errors':0,'seconds':0.0,'max_seconds':0.0})
        row['calls']+=1
        start=time.perf_counter()
        try:
            return operation(*args,**kwargs)
        except BaseException:
            row['errors']+=1
            raise
        finally:
            elapsed=time.perf_counter()-start
            row['seconds']+=elapsed
            row['max_seconds']=max(row['max_seconds'],elapsed)

    @contextmanager
    def native_calls(self, session_class):
        original=session_class._call
        def observed(instance,op,**fields):
            return self.invoke('native:'+op,original,instance,op,**fields)
        with patch.object(session_class,'_call',observed):
            yield

    @contextmanager
    def function(self, module, name, label):
        original=getattr(module,name)
        def observed(*args,**kwargs):
            return self.invoke(label,original,*args,**kwargs)
        with patch.object(module,name,observed):
            yield
