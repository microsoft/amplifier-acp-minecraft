"""Domain journal for explicit native source exchanges under a closed game gate.

The shared driver owns platform identity, pointers and no-replace renames. This
module owns exactly-once phase selection and observes lost replies; it never
retries an uncertain rename, deletes a baseline, or resumes a game listener.
"""
from pathlib import Path
import uuid
from installation_guard import ContinuityError, digest, durable_write, read, service_stopped


class NativeExchange:
    def __init__(self, cfg, session, backend, transaction, operation, targets):
        for value in (transaction, operation):
            if str(uuid.UUID(value)) != value:raise ValueError('Canonical exchange IDs required')
        if set(targets) != {'app','venv'}:raise ValueError('Exact app and environment targets required')
        self.cfg,self.session,self.backend=cfg,session,backend
        self.home,self.state=Path(cfg['home']),Path(cfg['state'])
        self.transaction,self.operation=transaction,operation
        self.path=self.state/'native-source-receipts'/(operation+'.json')
        self.targets=targets
        driver=read(cfg['native_platform']['config'])
        for key,target in targets.items():
            if target.get('root')!='state' or not isinstance(target.get('path'),str):
                raise ValueError('Source candidates must remain in owner state')
            relative=Path(target['path'])
            if relative.is_absolute() or '..' in relative.parts or len(relative.parts)<2:
                raise ValueError('Explicit non-traversing candidate child required')
            entry=driver.get('exchanges',{}).get(key,{})
            if entry != {'lock':'installation','profile':{'current':str(self.home/key),'roots':{'state':str(self.state)}}}:
                raise ValueError('Native source exchange is not bound to this installation')
        self.binding=digest({'transaction':transaction,'operation':operation,'targets':targets,'config':cfg})
        self.value=read(self.path) if self.path.exists() else None
        if self.value and self.value.get('binding')!=self.binding:
            raise ContinuityError('Native exchange operation changed')

    def save(self):durable_write(self.path,self.value)

    def closed(self):
        gate=read(self.home/'installation-updates/gate.json')
        receipt=read(self.state/'transactions'/(self.transaction+'.json'))
        if (gate!={'version':1,'transaction_id':self.transaction,'closed':True}
                or receipt.get('phase')!='ready' or receipt.get('config_hash')!=digest(self.cfg)
                or receipt.get('game') is not True
                or any(not service_stopped(v) for v in self.backend.services().values())):
            raise ContinuityError('Native source exchange needs the same settled game gate')

    def entry(self,key,phase):
        return {'root':'state','path':f'native-source/{self.operation}/{key}-{phase}'}

    def observe(self,key,phase):return self.session.exchange_inspect(key,self.entry(key,phase))

    def reconcile(self,key,step):
        expected=step['after'];current=self.session.exchange_inspect(key)
        incoming=self.observe(key,step['incoming']);retained=self.observe(key,step['retained'])
        if current!=expected or incoming is not None or retained!=step['before']:
            raise ContinuityError('Native exchange outcome is uncertain; preserve all entries without retry')
        step['state']='settled';self.save()
        return {'current':current,'retained':retained}

    def transfer(self,key,direction,before,after,incoming,retained):
        row=self.value['entries'][key]
        step=row.get(direction)
        if step:
            # A reply lost before the receipt write is settled by exact observed
            # identities only. An unchanged pre-dispatch view is not retry proof.
            return self.reconcile(key,step)
        if (self.session.exchange_inspect(key)!=before
                or self.observe(key,incoming)!=after or self.observe(key,retained) is not None):
            raise ContinuityError('Native source identity changed before exchange')
        step={'state':'intent','before':before,'after':after,'incoming':incoming,'retained':retained}
        row[direction]=step;self.save()
        self.session.exchange_apply(key,self.entry(key,incoming),self.entry(key,retained),before,after)
        return self.reconcile(key,step)

    def apply(self):
        self.closed()
        if self.value and self.value.get('phase') in ('rolling_back','rolled_back'):
            raise ContinuityError('Rolled back source operation cannot be reapplied')
        if self.value is None:
            self.value={'schema':1,'binding':self.binding,'transaction':self.transaction,'phase':'preparing','entries':{}}
            self.save()
        self.session.private_dir('state','native-source')
        self.session.private_dir('state','native-source/'+self.operation)
        for key,target in self.targets.items():
            row=self.value['entries'].get(key)
            if row is None:
                before=self.session.exchange_inspect(key);candidate=self.session.exchange_inspect(key,target)
                if before is None or not candidate or candidate.get('kind')!='directory':
                    raise ContinuityError('Current source and direct candidate directory required')
                if self.observe(key,'incoming') is not None or self.observe(key,'baseline') is not None:
                    raise ContinuityError('New source operation already has artifacts')
                row={'before':before,'target':candidate,'prepare':'intent'}
                self.value['entries'][key]=row;self.save()
                prepared=self.session.exchange_prepare_pointer(key,self.entry(key,'incoming'),target,candidate)
                row.update(prepare='settled',prepared=prepared);self.save()
            if row['prepare']!='settled':
                observed=self.observe(key,'incoming')
                if (not observed or observed.get('kind')!='pointer'
                        or observed.get('target_identity')!=row['target'].get('identity')
                        or self.session.exchange_inspect(key,target)!=row['target']):
                    raise ContinuityError('Pointer preparation unknown; never repeat creation')
                row.update(prepare='settled',prepared=observed);self.save()
            self.transfer(key,'apply',row['before'],row['prepared'],'incoming','baseline')
        self.value['phase']='applied';self.save()
        return {'applied':True,'receipt':str(self.path)}

    def rollback(self):
        self.closed()
        if not self.value:raise ContinuityError('No source exchange receipt to roll back')
        self.value['phase']='rolling_back';self.save()
        for key in reversed(list(self.targets)):
            row=self.value['entries'].get(key)
            if not row or not row.get('apply'):
                if row and self.session.exchange_inspect(key)!=row['before']:
                    raise ContinuityError('Unapplied source changed independently')
                continue
            if row.get('rollback'):
                self.reconcile(key,row['rollback']);continue
            self.reconcile(key,row['apply'])
            self.transfer(key,'rollback',row['prepared'],row['before'],'baseline','rejected')
        self.value['phase']='rolled_back';self.save()
        return {'rolled_back':True,'receipt':str(self.path)}
