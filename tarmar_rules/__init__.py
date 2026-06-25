"""tarmar-rules — the Tarmar d20 combat-resolution core, shared across games.

The single source of truth for the weapon-class x armour-tier Target-Number
matrix and the d20 roll-over resolution (to-hit modifiers, the under-strength
penalty, crit/fumble, and the Hybrid armour rule). Carries no game-specific data
(weapons, armour, figures) — each game tags its own catalog with a
``weapon_class`` / ``armour_tier`` and calls these pure functions.

Used by ``tarmar-studio`` (the Django app) and ``melee`` (the standalone game),
so the rules can't drift between them. Design rationale and the locked
hit-chance surface live in tarmar-studio's
``reference/content/proposals/d20-combat-resolution-spec.md``.
"""
from __future__ import annotations

from .combat import (
    ARMOUR_TIERS,
    HEAVY_CLASSES,
    MATRIX,
    damage_after_armour,
    dex_modifier,
    dodge_modifier,
    hit_probability,
    resolve_attack,
    skill_bonus,
    strength_fit_penalty,
    target_number,
    to_hit_bonus,
)

__all__ = [
    "ARMOUR_TIERS",
    "HEAVY_CLASSES",
    "MATRIX",
    "damage_after_armour",
    "dex_modifier",
    "dodge_modifier",
    "hit_probability",
    "resolve_attack",
    "skill_bonus",
    "strength_fit_penalty",
    "target_number",
    "to_hit_bonus",
]
