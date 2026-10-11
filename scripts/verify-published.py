"""Wait for registry processing and verify published bytes. Never uploads or republishes."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import urllib.error
import urllib.request


def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"Cache-Control": "no-cache"}), timeout=20) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise


def verify(version, folder, timeout):
    expected = {
        "npm": folder / f"claude-webdesk-{version}.tgz",
        "wheel": folder / f"claude_webdesk-{version}-py3-none-any.whl",
        "sdist": folder / f"claude_webdesk-{version}.tar.gz",
    }
    for artifact in expected.values():
        if not artifact.is_file():
            raise RuntimeError(f"Missing original release artifact: {artifact.name}")
    deadline = time.monotonic() + timeout
    while True:
        try:
            npm = get(f"https://registry.npmjs.org/claude-webdesk/{version}")
            pypi = get(f"https://pypi.org/pypi/claude-webdesk/{version}/json")
            latest = get("https://registry.npmjs.org/claude-webdesk/latest")
            files = {item["filename"]: item for item in (pypi or {}).get("urls", [])}
            if npm and npm.get("version") == version and latest and latest.get("version") == version and all(expected[key].name in files for key in ("wheel", "sdist")):
                if npm["dist"]["shasum"] != hashlib.sha1(expected["npm"].read_bytes()).hexdigest():
                    raise RuntimeError("Published npm bytes differ from the release artifact")
                for key in ("wheel", "sdist"):
                    if files[expected[key].name]["digests"]["sha256"] != hashlib.sha256(expected[key].read_bytes()).hexdigest():
                        raise RuntimeError(f"Published {key} bytes differ from the release artifact")
                print(f"npm/PyPI {version}: visible, latest npm tag verified, all artifact digests match.", flush=True)
                return
        except (OSError, urllib.error.URLError) as error:
            print(f"Registry temporarily unavailable: {type(error).__name__}", flush=True)
        if time.monotonic() >= deadline:
            raise RuntimeError("Registry visibility timed out. Check processing status; do not republish blindly.")
        print("Waiting for npm/PyPI processing/index propagation; no additional upload.", flush=True)
        time.sleep(20)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--folder", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=1200)
    args = parser.parse_args()
    verify(args.version, args.folder, args.timeout)
