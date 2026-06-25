"""Pure-pytest guard for the shared Tarmar combat core.

Mirrors the locks from tarmar-studio's Django test_combat.py (minus the
catalog/model integration): the modifier math, the §3.1 under-strength rule, the
crit/fumble resolution, the Hybrid armour rule, and the published balance
surface (Untrained + Master grids), so a matrix edit that shifts balance fails
loudly in the one place the rules now live.
"""
from __future__ import annotations

import pytest

from tarmar_rules import combat


def test_dex_modifier_floors_toward_negative() -> None:
    assert combat.dex_modifier(10) == 0
    assert combat.dex_modifier(14) == 2
    assert combat.dex_modifier(18) == 4
    assert combat.dex_modifier(9) == -1


def test_dodge_modifier_floors_at_zero() -> None:
    assert combat.dodge_modifier(8) == 0
    assert combat.dodge_modifier(16) == 3


def test_skill_bonus_ladder() -> None:
    assert combat.skill_bonus(0) == 0
    assert combat.skill_bonus(3) == 6
    assert combat.skill_bonus(-1) == 0


def test_under_strength_penalty_equals_shortfall() -> None:
    assert combat.strength_fit_penalty(12, 12) == 0
    assert combat.strength_fit_penalty(16, 12) == 0  # excess gives no bonus
    assert combat.strength_fit_penalty(11, 14) == -3
    assert combat.strength_fit_penalty(3, None) == 0


def test_to_hit_bonus_combines_sources() -> None:
    assert combat.to_hit_bonus(
        effective_dexterity=12, skill_level=0, effective_strength=11, str_req=14
    ) == -2


def test_target_number_and_shield_dodge() -> None:
    assert combat.target_number("Piercing", "Heavy") == 22
    assert combat.target_number(
        "Striking", "None", shield_bonus=2, defender_dodge=3
    ) == 18
    with pytest.raises(KeyError):
        combat.target_number("Nonsense", "Heavy")


def test_resolve_natural_rolls() -> None:
    assert combat.resolve_attack(20, a_target_number=99, bonus=0)["critical"]
    assert combat.resolve_attack(1, a_target_number=2, bonus=10)["fumble"]
    assert combat.resolve_attack(12, a_target_number=15, bonus=4)["hit"]
    assert not combat.resolve_attack(9, a_target_number=15, bonus=4)["hit"]
    with pytest.raises(ValueError):
        combat.resolve_attack(21, a_target_number=10, bonus=0)


def test_hybrid_armour() -> None:
    assert combat.damage_after_armour(9, 5, "Striking", "Heavy") == 4
    assert combat.damage_after_armour(9, 5, "Heavy Striking", "Heavy") == 7
    assert combat.damage_after_armour(9, 3, "Heavy Striking", "Medium") == 6
    assert combat.damage_after_armour(2, 5, "Piercing", "Heavy") == 0


EXPECTED_UNTRAINED = {
    "Piercing": (0.50, 0.35, 0.15, 0.05),
    "Striking": (0.40, 0.35, 0.25, 0.15),
    "Thrusting": (0.45, 0.35, 0.25, 0.10),
    "Heavy Striking": (0.35, 0.35, 0.30, 0.25),
    "Heavy Thrusting": (0.35, 0.35, 0.30, 0.30),
    "Missile — Bows": (0.45, 0.35, 0.20, 0.05),
    "Missile — Crossbows": (0.40, 0.35, 0.30, 0.25),
    "Flexible / Snare": (0.40, 0.25, 0.10, 0.05),
}
EXPECTED_MASTER = {
    "Piercing": (0.80, 0.65, 0.45, 0.25),
    "Striking": (0.70, 0.65, 0.55, 0.45),
    "Thrusting": (0.75, 0.65, 0.55, 0.40),
    "Heavy Striking": (0.65, 0.65, 0.60, 0.55),
    "Heavy Thrusting": (0.65, 0.65, 0.60, 0.60),
    "Missile — Bows": (0.75, 0.65, 0.50, 0.35),
    "Missile — Crossbows": (0.70, 0.65, 0.60, 0.55),
    "Flexible / Snare": (0.70, 0.55, 0.40, 0.25),
}


@pytest.mark.parametrize(
    "expected,skill_level", [(EXPECTED_UNTRAINED, 0), (EXPECTED_MASTER, 3)]
)
def test_balance_surface(expected, skill_level) -> None:
    bonus = combat.skill_bonus(skill_level)
    for weapon_class, row in expected.items():
        for tier, chance in zip(combat.ARMOUR_TIERS, row):
            target = combat.target_number(weapon_class, tier)
            assert combat.hit_probability(target, bonus) == pytest.approx(chance)
