import argparse
import json
from pathlib import Path

from adapter import control


def main():
    parser = argparse.ArgumentParser(description="Inspect, stop, or resume this Minecraft connection")
    parser.add_argument("--home", type=Path, required=True)
    parser.add_argument("operation", choices=["state", "stop", "resume"])
    args = parser.parse_args()
    cfg = json.loads((args.home.expanduser() / "config.json").read_bytes())
    response = control(cfg, "/" + args.operation, {} if args.operation != "state" else None)
    print(json.dumps(response, indent=2))


if __name__ == "__main__":
    main()
