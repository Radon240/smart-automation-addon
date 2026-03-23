import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Set
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from storage.options_store import load_options, resolve_enabled_domains


def _read_first_existing(paths: List[str]) -> str:
    for path in paths:
        p = Path(path)
        if p.exists():
            try:
                value = p.read_text(encoding="utf-8").strip()
                if value:
                    return value
            except Exception:
                continue
    return ""


def get_supervisor_token() -> str:
    token = (os.getenv("SUPERVISOR_TOKEN") or "").strip()
    if token:
        return token

    token = (os.getenv("HASSIO_TOKEN") or "").strip()
    if token:
        return token

    return _read_first_existing(
        [
            "/run/s6/container_environment/SUPERVISOR_TOKEN",
            "/run/s6/container_environment/HASSIO_TOKEN",
        ]
    )


def get_supervisor_api_url() -> str:
    raw = (
        os.getenv("SUPERVISOR_API_URL")
        or os.getenv("HASSIO_URL")
        or "http://supervisor/core/api"
    ).strip()
    if raw.endswith("/"):
        raw = raw[:-1]
    if not raw.endswith("/api"):
        raw = f"{raw}/api"
    return raw


def _flatten_history_payload(payload: Any) -> List[Dict[str, Any]]:
    if not isinstance(payload, list):
        return []

    flattened: List[Dict[str, Any]] = []
    for entry in payload:
        if isinstance(entry, list):
            for item in entry:
                if isinstance(item, dict):
                    flattened.append(item)
        elif isinstance(entry, dict):
            flattened.append(entry)
    return flattened


def fetch_states(base_url: str, supervisor_token: str) -> List[Dict[str, Any]]:
    states_url = f"{base_url}/states"
    req = Request(
        states_url,
        headers={
            "Authorization": f"Bearer {supervisor_token}",
            "Content-Type": "application/json",
        },
        method="GET",
    )

    try:
        with urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
        payload = json.loads(raw)
    except Exception as e:
        raise RuntimeError(f"Failed to fetch entity list from {states_url}: {e}") from e

    if not isinstance(payload, list):
        raise RuntimeError("Invalid /states response format")
    return [item for item in payload if isinstance(item, dict)]


def collect_domain_counts(states: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for item in states:
        entity_id = str(item.get("entity_id") or "").strip()
        if "." not in entity_id:
            continue
        domain = entity_id.split(".", 1)[0]
        counts[domain] = counts.get(domain, 0) + 1
    return counts


def fetch_trainable_entity_ids(states: List[Dict[str, Any]], enabled_domains: Set[str]) -> List[str]:
    entity_ids: List[str] = []
    for item in states:
        entity_id = str(item.get("entity_id") or "").strip()
        if "." not in entity_id:
            continue
        domain = entity_id.split(".", 1)[0]
        if domain in enabled_domains:
            entity_ids.append(entity_id)

    seen = set()
    unique_ids: List[str] = []
    for entity_id in entity_ids:
        if entity_id in seen:
            continue
        seen.add(entity_id)
        unique_ids.append(entity_id)
    return unique_ids


def fetch_history_from_home_assistant(history_days: int) -> List[Dict[str, Any]]:
    supervisor_token = get_supervisor_token()
    if not supervisor_token:
        raise RuntimeError(
            "Supervisor token is missing. Checked SUPERVISOR_TOKEN, HASSIO_TOKEN "
            "and /run/s6/container_environment/*"
        )

    options = load_options()
    base_url = get_supervisor_api_url().rstrip("/")
    states = fetch_states(base_url, supervisor_token)
    available_domains = set(collect_domain_counts(states).keys())
    enabled_domains = resolve_enabled_domains(options, available_domains)
    entity_ids = fetch_trainable_entity_ids(states, enabled_domains)
    if not entity_ids:
        raise RuntimeError(
            "No trainable entities found in /states. Enabled domains: "
            + ", ".join(sorted(enabled_domains))
        )

    filter_entity_id = ",".join(entity_ids)
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=history_days)
    start_iso = start_time.isoformat().replace("+00:00", "Z")
    end_iso = end_time.isoformat().replace("+00:00", "Z")

    query_url = (
        f"{base_url}/history/period?"
        f"{urlencode({'start_time': start_iso, 'end_time': end_iso, 'filter_entity_id': filter_entity_id})}"
    )
    path_url = (
        f"{base_url}/history/period/{quote(start_iso, safe='')}?"
        f"{urlencode({'end_time': end_iso, 'filter_entity_id': filter_entity_id})}"
    )

    last_error = "unknown error"
    for url in [query_url, path_url]:
        req = Request(
            url,
            headers={
                "Authorization": f"Bearer {supervisor_token}",
                "Content-Type": "application/json",
            },
            method="GET",
        )
        try:
            with urlopen(req, timeout=20) as resp:
                raw = resp.read().decode("utf-8")
            payload = json.loads(raw)
            return _flatten_history_payload(payload)
        except HTTPError as e:
            try:
                body = e.read().decode("utf-8")
            except Exception:
                body = ""
            last_error = f"HTTP {e.code} for {url}. body={body[:400]}"
        except URLError as e:
            last_error = f"Connection error for {url}: {e.reason}"
        except Exception as e:
            last_error = f"Unexpected error for {url}: {e}"

    raise RuntimeError(f"Home Assistant history request failed: {last_error}")
