import os
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parent / "config.yml"


def _load() -> dict:
    try:
        with CONFIG_PATH.open() as handle:
            return yaml.safe_load(handle) or {}
    except FileNotFoundError:
        return {}


def _int_list(raw: str) -> list[int]:
    return [int(part) for part in raw.replace(" ", "").split(",") if part]


config = _load()

_database = dict(config.get("database") or {})

if os.environ.get("DATABASE_URL"):
    _database["url"] = os.environ["DATABASE_URL"]
_database.setdefault("pool", {})
_database["pool"].setdefault("timeout", 10)
_database["pool"].setdefault("max_size", 10)
database = _database

_telegram = dict(config.get("telegram") or {})
if os.environ.get("TELEGRAM_TOKEN"):
    _telegram["token"] = os.environ["TELEGRAM_TOKEN"]
telegram = _telegram

_met_api = dict(config.get("met-api") or {})
if os.environ.get("MET_USER_AGENT"):
    _met_api["user-agent-header"] = os.environ["MET_USER_AGENT"]
met_api = _met_api

_users = dict(config.get("users") or {})
if os.environ.get("TEST_USERS"):
    _users["test-users"] = _int_list(os.environ["TEST_USERS"])
if os.environ.get("ADMIN_USERS"):
    _users["admin-users"] = _int_list(os.environ["ADMIN_USERS"])
_users.setdefault("test-users", [])
_users.setdefault("admin-users", [])
users = _users

_web = dict(config.get("web") or {})
_vapid = dict(_web.get("vapid") or {})
for env_name, key in (
    ("VAPID_PUBLIC_KEY", "public-key"),
    ("VAPID_PRIVATE_KEY", "private-key"),
    ("VAPID_CONTACT", "contact"),
):
    if os.environ.get(env_name):
        _vapid[key] = os.environ[env_name]
_web["vapid"] = _vapid
_web.setdefault("host", "0.0.0.0")
_web["port"] = int(os.environ.get("PORT") or _web.get("port") or 8000)
web = _web

# delete JSON responses in data/ older than this many days. Unset keeps them all
data_retention_days = os.environ.get("DATA_RETENTION_DAYS") or (
    config.get("data") or {}
).get("retention-days")
if data_retention_days is not None:
    data_retention_days = int(data_retention_days)

# should set INFO on env
log_level = (os.environ.get("LOG_LEVEL") or config.get("log-level") or "DEBUG").upper()


def missing_settings() -> list[str]:
    missing = []
    if not (database.get("url") or database.get("name")):
        missing.append("database (config.yml database:, or DATABASE_URL)")
    if not telegram.get("token"):
        missing.append("telegram token (config.yml telegram.token, or TELEGRAM_TOKEN)")
    if not met_api.get("user-agent-header"):
        missing.append("MET user agent (config.yml met-api, or MET_USER_AGENT)")
    return missing
