"""Path-based permission rules for out-of-workspace file access.

When a file tool is invoked with ``scope=system`` (i.e. targeting a path
outside the workspace sandbox), access is governed by per-directory rules
instead of a single global capability. Rules are stored as directory paths;
a rule covers the directory itself and everything beneath it (prefix match).

``check_permission`` returns one of ``"allow"`` / ``"deny"`` / ``"prompt"``.
``"prompt"`` means no rule matched and the caller should ask the operator
(allow once / always allow this directory / deny).
"""

from __future__ import annotations

import os
from typing import Dict


def _norm(p: str) -> str:
    return os.path.normpath(os.path.realpath(p)).lower()


def matches_dir(target: str, dir_rule: str) -> bool:
    """True if ``target`` is ``dir_rule`` or somewhere beneath it."""
    t = _norm(target)
    d = _norm(dir_rule)
    if not d:
        return False
    if t == d:
        return True
    sep = os.sep
    return t.startswith(d + sep)


def check_permission(target_path: str, op: str, rules: Dict) -> str:
    """Decide access for ``op`` ('read'|'write') on ``target_path``.

    ``rules`` is ``{"read": {"allow": [...], "deny": [...]}, "write": {...}}``.
    Deny takes precedence over allow. No match -> ``"prompt"``.
    """
    op_rules = rules.get(op, {}) or {}
    for d in op_rules.get("deny", []) or []:
        if matches_dir(target_path, d):
            return "deny"
    for d in op_rules.get("allow", []) or []:
        if matches_dir(target_path, d):
            return "allow"
    return "prompt"


def parent_dir_of(path: str) -> str:
    """The directory to record when the user picks 'always allow'."""
    real = os.path.realpath(path)
    if os.path.isdir(real):
        return real
    return os.path.dirname(real) or real
