import unittest
from unittest.mock import AsyncMock
from pathlib import Path
import tempfile
from watches import Watches


class WatchTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_optional_bridge_outage_does_not_abort_planner_or_substitute_policy(self):
        with tempfile.TemporaryDirectory() as d:
            req=AsyncMock(side_effect=RuntimeError('unavailable'))
            w=Watches(Path(d),{},req,lambda *a,**kw:None);w.transport.evaluate=AsyncMock()
            await w.poll()
            self.assertEqual(await w.pending(),[])
            self.assertTrue(await w.managed())
            await w.acknowledge([{'id':'pending'}])
            w.transport.evaluate.assert_not_called()
    async def test_shadow_routes_result_and_failure_releases_pending_without_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            req=AsyncMock(side_effect=[{'token':'a','request':{'state':{},'questions':[]}}, {'receipts':[]}])
            w=Watches(Path(d),{'mode':'shadow'},req,lambda *a,**kw:None)
            w.transport.evaluate=AsyncMock(return_value=({'answers':[]},42))
            await w.poll()
            self.assertTrue(req.call_args_list[1].args[1]['observe_only'])
            await w.poll();self.assertEqual(req.call_count,2)
        with tempfile.TemporaryDirectory() as d:
            req=AsyncMock(side_effect=[{'token':'a','request':{'state':{},'questions':[]}}, {'abandoned':True}])
            w=Watches(Path(d),{'mode':'advisory'},req,lambda *a,**kw:None)
            w.transport.evaluate=AsyncMock(side_effect=RuntimeError('outage'))
            await w.poll()
            self.assertEqual(req.call_args_list[1].args[1],{'operation':'abandon','token':'a'})

    async def test_no_event_skips_provider_and_only_triggered_notifications_are_delivered(self):
        with tempfile.TemporaryDirectory() as d:
            req=AsyncMock(return_value={'skip':'no_new_selected_evidence'})
            w=Watches(Path(d),{},req,lambda *a,**kw:None);w.transport.evaluate=AsyncMock()
            await w.poll();w.transport.evaluate.assert_not_called()
            req.return_value={'watches':[{'status':'cancelled','notification':{'id':'old'}},
                                        {'status':'armed','notification':None},
                                        {'status':'triggered','notification':{'id':'ready'}}]}
            self.assertEqual(await w.pending(),[{'id':'ready'}])
            await w.acknowledge([{'id':'ready'}])
            self.assertEqual(req.call_args.args[1],{'operation':'ack','id':'ready'})
