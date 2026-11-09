import json,os,subprocess,sys,tempfile,unittest
from pathlib import Path

SCRIPT=Path(__file__).resolve().parents[1]/'ops/enable_screenshots.py'
class ScreenshotSetupTests(unittest.TestCase):
    def run_setup(self,success,custom=False):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);root=Path(tmp.name)
        app=root/'app';app.mkdir();config=root/'config.json';config.write_text(json.dumps({'username':'Player','token':'unchanged'}))
        if custom:
            browser=root/'custom-browser';browser.touch();config.write_text(json.dumps({'username':'Player','token':'unchanged','screenshots':{'enabled':True,'browser_path':str(browser)}}))
        node=root/'node';node.write_text('#!'+sys.executable+'\nimport sys\nsys.exit('+('0' if success else '1')+')\n');node.chmod(0o700)
        result=subprocess.run([sys.executable,str(SCRIPT),'--config',str(config),'--directory',str(root/'images'),'--node',str(node),'--app',str(app)],capture_output=True,text=True)
        return root,config,result
    def test_failed_browser_readiness_preserves_config_without_creating_store(self):
        root,config,result=self.run_setup(False);self.assertNotEqual(result.returncode,0)
        self.assertEqual(json.loads(config.read_text()),{'username':'Player','token':'unchanged'});self.assertFalse((root/'images').exists())
    def test_ready_browser_enables_only_screenshots_without_service_operation(self):
        root,config,result=self.run_setup(True);self.assertEqual(result.returncode,0,result.stderr)
        value=json.loads(config.read_text());self.assertEqual(value['token'],'unchanged');self.assertEqual(value['screenshots'],{'enabled':True,'directory':str(root/'images')});self.assertEqual(config.stat().st_mode&0o777,0o600)

    def test_existing_custom_browser_is_preserved_without_an_override(self):
        root,config,result=self.run_setup(True,custom=True);self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(config.read_text())['screenshots']['browser_path'],str(root/'custom-browser'))
