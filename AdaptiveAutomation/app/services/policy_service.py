from __future__ import annotations

from typing import Any, Dict, Iterable, List, Set


def _domain(entity_id: str) -> str:
    if "." not in entity_id:
        return "unknown"
    return entity_id.split(".", 1)[0]


def _to_set(value: Any) -> Set[str]:
    if not isinstance(value, list):
        return set()
    return {
        str(x).strip()
        for x in value
        if isinstance(x, str) and str(x).strip()
    }


def apply_policy(rules: Iterable[Dict[str, Any]], options: Dict[str, Any]) -> List[Dict[str, Any]]:
    domain_allow = _to_set(options.get("policy_domain_allowlist"))
    domain_deny = _to_set(options.get("policy_domain_denylist"))
    entity_allow = _to_set(options.get("policy_entity_allowlist"))
    entity_deny = _to_set(options.get("policy_entity_denylist"))
    one_per_entity = bool(options.get("policy_one_per_entity", False))

    filtered: List[Dict[str, Any]] = []
    for rule in rules:
        entity_id = str(rule.get("entity_id") or "")
        domain = str(rule.get("domain") or _domain(entity_id))

        if entity_allow and entity_id and entity_id not in entity_allow:
            continue
        if domain_allow and domain and domain not in domain_allow:
            continue
        if entity_id and entity_id in entity_deny:
            continue
        if domain and domain in domain_deny:
            continue

        filtered.append(rule)

    if not one_per_entity:
        return filtered

    best: Dict[str, Dict[str, Any]] = {}
    for rule in filtered:
        entity_id = str(rule.get("entity_id") or "")
        if not entity_id:
            continue
        curr = best.get(entity_id)
        if curr is None or float(rule.get("score", 0.0)) > float(curr.get("score", 0.0)):
            best[entity_id] = rule

    # Keep non-entity rules too.
    entity_bound = set(best.keys())
    result = [r for r in filtered if not str(r.get("entity_id") or "")]
    result.extend(best[eid] for eid in sorted(entity_bound))
    return result
