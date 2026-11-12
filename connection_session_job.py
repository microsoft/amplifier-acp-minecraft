"""Read-only verification child for bounded status-polled owner Connect."""
import argparse
import asyncio
from contextlib import ExitStack
from pathlib import Path
from installation_guard import durable_write, read
from installation_session_probe import probe


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--home', required=True, type=Path)
    parser.add_argument('--result', required=True, type=Path)
    parser.add_argument('--native-owner-config', type=Path)
    args = parser.parse_args()
    if not args.home.is_absolute() or not args.result.is_absolute() or args.result.exists():
        raise ValueError('Fresh absolute owner job paths required')
    native=None
    with ExitStack() as stack:
        if args.native_owner_config:
            from installation_native import native_scope, NativeIO
            cfg=read(args.native_owner_config)
            if Path(cfg['home']).resolve()!=args.home.resolve():
                raise ValueError('Probe enrollment belongs to a different game connection')
            session=stack.enter_context(native_scope(cfg))
            native=(cfg['native_platform']['driver'],cfg['native_platform']['config'])
            root,_=NativeIO(cfg,session).relative(args.result)
            if root!='state':raise ValueError('Probe result must remain under owner state')
        try:
            result = asyncio.run(probe(args.home, 180, idle_timeout=30, native_driver=native))
        except Exception as error:
            result = {'verified':False, 'failure_type':type(error).__name__,
                      'message':'Original-session compatibility could not be verified; no prompt or replacement session was sent.'}
            if (getattr(error,'request_rejected',False) is True
                    and getattr(error,'request_method',None) in ('initialize','session/load')
                    and type(getattr(error,'request_error_code',None)) is int):
                result.update(failure_settled=True, request_method=error.request_method,
                              request_error_code=error.request_error_code,
                              new_session_created=False, prompt_sent=False)
        durable_write(args.result, result)


if __name__ == '__main__':
    main()
