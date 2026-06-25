"""d20 combat resolution — weapon-vs-armour Target Numbers and modifiers.

This module is the **single source of truth** for the d20 attack-resolution
system specified in
``reference/content/proposals/d20-combat-resolution-spec.md``. The spec's §6
matrix is mirrored here as :data:`MATRIX`; ``test_combat.py`` drift-guards the
markdown table against this code (same pattern as ``test_rules_consistency``).

Resolution is roll-over: ``d20 + to-hit bonus >= Target Number`` is a hit. The
Target Number's *base* difficulty comes entirely from the weapon class vs the
defender's armour tier (:func:`target_number`); DEX, skill, and the
under-strength penalty are *modifiers* on the d20 (:func:`to_hit_bonus`). A
natural 20 always hits (and crits); a natural 1 always misses (and fumbles).
"""

import math

# §6 — base Target Number by weapon class and armour tier. Source of truth.
ARMOUR_TIERS: tuple[str, ...] = ("None", "Light", "Medium", "Heavy")
MATRIX: dict[str, dict[str, int]] = {
    "Piercing": {"None": 11, "Light": 14, "Medium": 18, "Heavy": 22},
    "Striking": {"None": 13, "Light": 14, "Medium": 16, "Heavy": 18},
    "Thrusting": {"None": 12, "Light": 14, "Medium": 16, "Heavy": 19},
    "Heavy Striking": {"None": 14, "Light": 14, "Medium": 15, "Heavy": 16},
    "Heavy Thrusting": {"None": 14, "Light": 14, "Medium": 15, "Heavy": 15},
    "Missile — Bows": {"None": 12, "Light": 14, "Medium": 17, "Heavy": 20},
    "Missile — Crossbows": {"None": 13, "Light": 14, "Medium": 15, "Heavy": 16},
    "Flexible / Snare": {"None": 13, "Light": 16, "Medium": 19, "Heavy": 22},
}

# §8 Hybrid armour rule: these classes' impact carries through plate, so vs a
# Heavy target they ignore half the armour's stops.
HEAVY_CLASSES: frozenset[str] = frozenset({"Heavy Striking", "Heavy Thrusting"})

# §3 modifier knobs.
DEX_MODIFIER_DIVISOR = 2  # floor((DEX - 10) / 2)
SKILL_BONUS_PER_LEVEL = (
    2  # skill level 0-5 -> +0..+10; tiers Trained/Expert/Master = +2/+4/+6
)
SHORTFALL_PENALTY_PER_POINT = (
    1  # §3.1 under-strength: -1 to hit per point under str_req
)


def dex_modifier(dexterity: int) -> int:
    """To-hit bonus from DEX: ``floor((DEX - 10) / DEX_MODIFIER_DIVISOR)``.

    Pass the attacker's *effective* dexterity (after aging). Can be negative.
    """
    return math.floor((dexterity - 10) / DEX_MODIFIER_DIVISOR)


def dodge_modifier(dexterity: int) -> int:
    """Defender's dodge added to the Target Number — DEX modifier, floored at 0."""
    return max(0, dex_modifier(dexterity))


def skill_bonus(skill_level: int) -> int:
    """To-hit bonus from weapon skill level (0-5), ``SKILL_BONUS_PER_LEVEL`` each."""
    return SKILL_BONUS_PER_LEVEL * max(0, skill_level)


def strength_fit_penalty(effective_strength: int, str_req: int | None) -> int:
    """§3.1 under-strength rule: penalty equal to the STR shortfall, else 0.

    Returns ``min(0, effective_strength - str_req)`` scaled by
    ``SHORTFALL_PENALTY_PER_POINT``. A weapon with no ``str_req`` never
    penalises. The result is zero or negative.
    """
    if not str_req:
        return 0
    shortfall = effective_strength - str_req
    if shortfall >= 0:
        return 0
    return shortfall * SHORTFALL_PENALTY_PER_POINT


def to_hit_bonus(
    *,
    effective_dexterity: int,
    skill_level: int,
    effective_strength: int,
    str_req: int | None,
    situational: int = 0,
) -> int:
    """Total bonus added to the attacker's d20 (§2).

    Sums DEX aim, weapon skill, the under-strength penalty, and any situational
    modifier (flank/prone/range, re-signed for roll-over).
    """
    return (
        dex_modifier(effective_dexterity)
        + skill_bonus(skill_level)
        + strength_fit_penalty(effective_strength, str_req)
        + situational
    )


def target_number(
    weapon_class: str,
    armour_tier: str,
    *,
    shield_bonus: int = 0,
    defender_dodge: int = 0,
) -> int:
    """Number the attacker must reach: matrix base + shield + defender dodge (§2).

    Raises:
        KeyError: if ``weapon_class`` or ``armour_tier`` is not in the matrix.
    """
    return MATRIX[weapon_class][armour_tier] + shield_bonus + defender_dodge


def hit_probability(a_target_number: int, bonus: int) -> float:
    """Exact P(hit) over all 20 die faces (nat 20 auto-hit, nat 1 auto-miss)."""
    hits = 0
    for face in range(1, 21):
        if face == 20:
            hits += 1
        elif face == 1:
            continue
        elif face + bonus >= a_target_number:
            hits += 1
    return hits / 20


def resolve_attack(die_roll: int, a_target_number: int, bonus: int) -> dict:
    """Resolve a single attack from an already-rolled d20.

    The die is passed in rather than rolled here so resolution stays pure and
    testable; callers roll via ``characters.dice``. Returns a dict with ``hit``
    (bool), ``total`` (die + bonus), ``critical``/``fumble`` flags, and
    ``outcome`` (a short label).
    """
    if not 1 <= die_roll <= 20:
        raise ValueError(f"d20 roll out of range: {die_roll}")
    total = die_roll + bonus
    if die_roll == 20:
        return {
            "hit": True,
            "total": total,
            "critical": True,
            "fumble": False,
            "outcome": "critical",
        }
    if die_roll == 1:
        return {
            "hit": False,
            "total": total,
            "critical": False,
            "fumble": True,
            "outcome": "fumble",
        }
    hit = total >= a_target_number
    return {
        "hit": hit,
        "total": total,
        "critical": False,
        "fumble": False,
        "outcome": "hit" if hit else "miss",
    }


def damage_after_armour(
    raw_damage: int, stops: int, weapon_class: str, armour_tier: str
) -> int:
    """Damage that gets through armour under the §8 Hybrid rule.

    Armour's ``stops`` reduce damage as usual, EXCEPT a Heavy Striking / Heavy
    Thrusting weapon against a Heavy-armour target ignores half the stops
    (``stops // 2`` applied) — impact transfers through plate. Floored at 0.
    """
    applied_stops = stops
    if weapon_class in HEAVY_CLASSES and armour_tier == "Heavy":
        applied_stops = stops // 2
    return max(0, raw_damage - applied_stops)
