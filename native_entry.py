"""Fixed package entry points, including isolated Python service launches."""
import runpy
import sys
from pathlib import Path

if __name__=='__main__':
    modules={'controller':'adapter','connection-probe':'connection_session_job',
             'session-probe':'installation_session_probe','participant':'installation_participant',
             'connection':'installation_connection','source-provider':'installation_source_provider'}
    if len(sys.argv)<2 or sys.argv[1] not in modules:
        raise SystemExit('Select one fixed Minecraft native entry point')
    module=modules[sys.argv[1]]
    sys.path.insert(0,str(Path(__file__).resolve().parent))
    sys.argv=[module,*sys.argv[2:]]
    runpy.run_module(module,run_name='__main__')
