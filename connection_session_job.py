"""Read-only verification child for bounded status-polled owner Connect."""
import argparse
import asyncio
from pathlib import Path
from installation_guard import durable_write
from installation_session_probe import probe


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--home', required=True, type=Path)
    parser.add_argument('--result', required=True, type=Path)
    args = parser.parse_args()
    if not args.home.is_absolute() or not args.result.is_absolute() or args.result.exists():
        raise ValueError('Fresh absolute owner job paths required')
    try:
        result = asyncio.run(probe(args.home, 180, idle_timeout=30))
    except Exception as error:
        result = {'verified':False, 'failure_type':type(error).__name__,
                  'message':'Original-session compatibility could not be verified; no prompt or replacement session was sent.'}
    durable_write(args.result, result)


if __name__ == '__main__':
    main()
