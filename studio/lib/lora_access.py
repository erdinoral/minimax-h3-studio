"""Local Civitai access key; never returned by the public API."""
import json
import os
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler

STORE = Path(__file__).resolve().parents[1] / "data" / "lora_access.json"


class DownloadRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is not None and urlparse(newurl).hostname != "civitai.com":
            redirected.remove_header("Authorization")
        return redirected


def key():
    if os.environ.get("CIVITAI_API_KEY"):
        return os.environ["CIVITAI_API_KEY"]
    if STORE.is_file():
        return str(json.loads(STORE.read_text(encoding="utf-8")).get("civitai_api_key") or "")
    return ""


def save(value):
    STORE.parent.mkdir(parents=True, exist_ok=True)
    temporary = STORE.with_suffix(".tmp")
    temporary.write_text(json.dumps({"civitai_api_key":value.strip()}), encoding="utf-8")
    temporary.replace(STORE)


def request_headers(url):
    headers={"User-Agent":"H3-Studio"}
    if urlparse(url).hostname == "civitai.com" and key():
        headers["Authorization"]="Bearer " + key()
    return headers
