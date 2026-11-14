"""Prepare an isolated copy of accepted fixtures with the canonical observer.

Neither the shared checkout nor packaged product bytes are modified. The
recorded baseline and successor hashes distinguish this test-only successor.
"""
import hashlib
import json
import shutil
from pathlib import Path


def prepare(shared, destination):
    frozen = Path(__file__).parent / "fixtures/close-evidence-63e9890"
    manifest = json.loads((frozen / "manifest.json").read_bytes())
    tests = shared / "tests/native_python"
    for name, record in manifest["files"].items():
        original = tests / name
        actual = hashlib.sha256(original.read_bytes()).hexdigest() if original.exists() else None
        if actual != record["base_sha256"]:
            raise ValueError(f"Unexpected shared fixture baseline: {name}")
        if hashlib.sha256((frozen / name).read_bytes()).hexdigest() != record["sha256"]:
            raise ValueError(f"Changed canonical observer: {name}")
    destination.mkdir(parents=True, exist_ok=False)
    shutil.copytree(tests, destination / "tests/native_python",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(shared / "support/python", destination / "support/python",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for name in manifest["files"]:
        shutil.copyfile(frozen / name, destination / "tests/native_python" / name)
    (destination / "fixture-provenance.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return destination / "tests/native_python", manifest
