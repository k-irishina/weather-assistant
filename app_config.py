from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parent / "config.yml"


def _load() -> dict:
    try:
        with CONFIG_PATH.open() as handle:
            return yaml.safe_load(handle)
    except FileNotFoundError:
        raise RuntimeError(
            f"No config file at {CONFIG_PATH}. "
            "Make sure config.yml is present."
        ) from None


config = _load()

database = config["database"]
telegram = config["telegram"]
met_api = config["met-api"]
users = config["users"]

# todo: prune JSON responses in data/ older than this many days.
data_retention_days = (config.get("data") or {}).get("retention-days")
