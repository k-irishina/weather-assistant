import hashlib
import hmac
import logging
import xml.etree.ElementTree as ElementTree
from datetime import date, datetime, timezone
from typing import Optional
from urllib.parse import quote, urlparse

import requests

import app_config

log = logging.getLogger(__name__)

REGION = "auto"
LINK_SECONDS = 2 * 24 * 60 * 60

_listed: dict[date, dict[str, str]] = {}  # UTC day -> file name -> link


def configured() -> bool:
    return all(app_config.media_bucket.values())


def presigned_url(key: str, signed_on: date, query: Optional[dict[str, str]] = None) -> str:
    bucket = app_config.media_bucket
    host = f"{bucket['name']}.{urlparse(bucket['endpoint']).netloc}"
    path = "/" + quote(key)
    day = signed_on.strftime("%Y%m%d")
    signed_at = day + "T000000Z"
    scope = f"{day}/{REGION}/s3/aws4_request"

    params = {
        **(query or {}),
        "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
        "X-Amz-Credential": f"{bucket['access_key_id']}/{scope}",
        "X-Amz-Date": signed_at,
        "X-Amz-Expires": str(LINK_SECONDS),
        "X-Amz-SignedHeaders": "host",
    }
    query_text = "&".join(
        f"{quote(name, safe='-_.~')}={quote(value, safe='-_.~')}"
        for name, value in sorted(params.items())
    )
    request_text = "\n".join(("GET", path, query_text, f"host:{host}", "", "host", "UNSIGNED-PAYLOAD"))
    to_sign = "\n".join((
        "AWS4-HMAC-SHA256", signed_at, scope, hashlib.sha256(request_text.encode()).hexdigest()
    ))

    signing_key = ("AWS4" + bucket["secret_access_key"]).encode()
    for part in (day, REGION, "s3", "aws4_request"):
        signing_key = hmac.new(signing_key, part.encode(), hashlib.sha256).digest()
    signature = hmac.new(signing_key, to_sign.encode(), hashlib.sha256).hexdigest()
    return f"https://{host}{path}?{query_text}&X-Amz-Signature={signature}"


def background_links() -> dict[str, str]:
    today = datetime.now(timezone.utc).date()
    if today not in _listed:
        response = requests.get(presigned_url("", today, {"list-type": "2"}), timeout=10)
        if response.status_code != 200:
            log.warning("Bucket returned %s", response.status_code)
            return {}
        names = [
            element.text for element in ElementTree.fromstring(response.content).iter()
            if element.tag.endswith("}Key")
        ]
        _listed.clear()
        _listed[today] = {name: presigned_url(name, today) for name in names}
    return _listed[today]
