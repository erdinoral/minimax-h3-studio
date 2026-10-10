"""Optional film adapters; verify before activation and reuse existing hashes."""
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.loras import CATALOG, LORAS_DIR, candidates, verify_download
from lib.lora_access import request_headers, DownloadRedirectHandler


def install(ids=None):
    selected = [s for s in CATALOG if s.get("sha256") and (not ids or s["id"] in ids)]
    LORAS_DIR.mkdir(parents=True, exist_ok=True)
    by_hash = {}
    for path in LORAS_DIR.glob("*.safetensors"):
        with path.open("rb") as stream:
            digest=hashlib.sha256()
            for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
                digest.update(chunk)
            by_hash[digest.hexdigest()] = path
    results = []
    for spec in selected:
        dest = LORAS_DIR / spec["file"]
        previous = by_hash.get(spec["sha256"])
        if previous:
            if previous.name not in candidates(spec):
                # Sidecar alias avoids duplicate weights under another filename.
                dest.hardlink_to(previous) if not dest.exists() else None
            print("Already installed:", spec["label"], flush=True)
            results.append({"id":spec["id"], "status":"reused"})
            continue
        tmp = dest.with_suffix(".safetensors.part")
        try:
            print("Downloading:", spec["label"], flush=True)
            req = urllib.request.Request(spec["url"], headers=request_headers(spec["url"]))
            opener = urllib.request.build_opener(DownloadRedirectHandler())
            with opener.open(req, timeout=60) as response, tmp.open("wb") as target:
                while chunk := response.read(4 * 1024 * 1024):
                    target.write(chunk)
            verify_download(tmp, spec)
            tmp.replace(dest)
            by_hash[spec["sha256"]] = dest
            results.append({"id":spec["id"], "status":"installed", "sha256":spec["sha256"]})
            print("Verified:", spec["label"], flush=True)
        except Exception as exc:
            tmp.unlink(missing_ok=True)
            results.append({"id":spec["id"], "status":"failed", "error":str(exc)})
            print("Unavailable:", spec["label"], str(exc), flush=True)
    report=Path(__file__).resolve().parents[1]/"data"/"film-lora-install.json"
    report.parent.mkdir(parents=True,exist_ok=True)
    report.write_text(json.dumps(results, indent=2),encoding="utf-8")
    return results


if __name__ == "__main__":
    rows=install(set(sys.argv[1:]) or None)
    sys.exit(1 if any(r["status"] == "failed" for r in rows) else 0)
