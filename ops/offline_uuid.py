"""Operator helper: the UUID of an offline-route player. Computes only; no server access."""
import argparse
import hashlib
import json
import re
import uuid


def offline_uuid(name):
    """UUID a Java server or proxy gives an unauthenticated login with this exact name.

    Equal to Java's UUID.nameUUIDFromBytes(("OfflinePlayer:" + name).getBytes(UTF_8)).
    Names are case-sensitive: another capitalisation is another player.
    """
    if not isinstance(name, str) or not re.fullmatch(r'[!-~]{1,16}', name):
        raise ValueError('A Java player name is 1-16 visible ASCII characters without spaces')
    digest = hashlib.md5(('OfflinePlayer:' + name).encode(), usedforsecurity=False).digest()
    return str(uuid.UUID(bytes=digest, version=3))


def whitelist_entry(name):
    """One element of the array in a server's whitelist.json."""
    return {'uuid': offline_uuid(name), 'name': name}


def main(argv=None):
    parser = argparse.ArgumentParser(description='Print the offline-mode UUID of a Java player name.')
    parser.add_argument('name', help='Exact, case-sensitive player name, such as the username in its config.json')
    parser.add_argument('--whitelist-entry', action='store_true',
                        help='Print an entry for the whitelist.json array instead of the bare UUID')
    args = parser.parse_args(argv)
    try:
        print(json.dumps(whitelist_entry(args.name)) if args.whitelist_entry else offline_uuid(args.name))
    except ValueError as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
