"""Pure-pytest guard for the shared Tarmar combat core.

Mirrors the locks from tarmar-studio's Django test_combat.py (minus the
catalog/model integration): the modifier math, the weapon-skill transfer
layer, the §3.1 under-strength rule, the integrated §7 crit/fumble
resolution, the Hybrid armour rule, and the published balance surface
(unskilled + skill-level-6 grids), so a matrix edit that shifts balance fails
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


# tarmar-studio #119 (2026-08-28) replaced the capped 0/2/4/6
# "Untrained/Trained/Expert/Master" ladder with +1/level, uncapped. These two
# tests used to pin that superseded ladder (including its SKILL_LEVEL_MAX
# clamp, now removed); they're rewritten below to pin the current rule.
def test_skill_bonus_is_one_per_level() -> None:
    assert combat.skill_bonus(0) == 0
    assert combat.skill_bonus(1) == 1
    assert combat.skill_bonus(3) == 3
    assert combat.skill_bonus(-1) == 0


def test_skill_bonus_is_uncapped() -> None:
    # No ceiling on level or bonus -- level N is always +N.
    for level in (6, 9, 17, 40):
        assert combat.skill_bonus(level) == level


def test_same_class_bonus_is_half_the_level_rounded_down() -> None:
    assert combat.same_class_skill_bonus(0) == 0
    assert combat.same_class_skill_bonus(1) == 0
    assert combat.same_class_skill_bonus(3) == 1
    assert combat.same_class_skill_bonus(4) == 2
    assert combat.same_class_skill_bonus(11) == 5
    assert combat.same_class_skill_bonus(-2) == 0


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


# Published balance surface (spec §6.1). Baseline: aim 0, STR-fit 0, no
# shield, dodge 0. At +1 per skill level (tarmar-studio #119) the published
# "+6" grid is skill level 6, not the old capped-ladder's level 3.
EXPECTED_UNSKILLED = {
    "Piercing": (0.50, 0.35, 0.15, 0.05),
    "Striking": (0.40, 0.35, 0.25, 0.15),
    "Thrusting": (0.45, 0.35, 0.25, 0.10),
    "Heavy Striking": (0.35, 0.35, 0.30, 0.25),
    "Heavy Thrusting": (0.35, 0.35, 0.30, 0.30),
    "Missile — Bows": (0.45, 0.35, 0.20, 0.05),
    "Missile — Crossbows": (0.40, 0.35, 0.30, 0.25),
    "Flexible / Snare": (0.40, 0.25, 0.10, 0.05),
}
EXPECTED_SKILL_SIX = {
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
    "expected,skill_level", [(EXPECTED_UNSKILLED, 0), (EXPECTED_SKILL_SIX, 6)]
)
def test_balance_surface(expected, skill_level) -> None:
    bonus = combat.skill_bonus(skill_level)
    for weapon_class, row in expected.items():
        for tier, chance in zip(combat.ARMOUR_TIERS, row):
            target = combat.target_number(weapon_class, tier)
            assert combat.hit_probability(target, bonus) == pytest.approx(chance)


def test_confirm_severe_crit_is_a_second_to_hit_roll() -> None:
    # Confirm hits the same TN with the same bonus -> severe.
    assert combat.confirm_severe_crit(15, a_target_number=13, bonus=0)
    assert not combat.confirm_severe_crit(8, a_target_number=13, bonus=0)
    # The bonus counts on the confirm too.
    assert combat.confirm_severe_crit(9, a_target_number=13, bonus=4)
    # Natural extremes apply: a 20 always confirms, a 1 never does.
    assert combat.confirm_severe_crit(20, a_target_number=99, bonus=0)
    assert not combat.confirm_severe_crit(1, a_target_number=2, bonus=10)
    with pytest.raises(ValueError):
        combat.confirm_severe_crit(0, a_target_number=10, bonus=0)


def test_fumble_table_covers_the_d6() -> None:
    assert [combat.fumble_result(face) for face in range(1, 7)] == [
        combat.FUMBLE_OFF_BALANCE,
        combat.FUMBLE_OFF_BALANCE,
        combat.FUMBLE_OFF_BALANCE,
        combat.FUMBLE_DROP,
        combat.FUMBLE_DROP,
        combat.FUMBLE_STRESS,
    ]
    with pytest.raises(ValueError):
        combat.fumble_result(7)


def test_crit_and_fumble_knobs() -> None:
    # New v0.3.0 names and their deprecated pre-v0.3.0 aliases (melee
    # imports the old names directly) must agree.
    assert combat.CRIT_DAMAGE_ROLLS == 2
    assert combat.SEVERE_CRIT_DAMAGE_ROLLS == 3
    assert combat.CRIT_DAMAGE_MULTIPLIER == combat.CRIT_DAMAGE_ROLLS
    assert combat.SEVERE_CRIT_DAMAGE_MULTIPLIER == combat.SEVERE_CRIT_DAMAGE_ROLLS
    assert combat.OFF_BALANCE_PENALTY == -2
    assert combat.DIE_FACES == 20
    assert combat.FUMBLE_DIE_SIDES == 6


# ---------------------------------------------------------------------------
# Weapon-skill transfer layer (tarmar-studio #119). This package has no
# weapon catalog, so unlike tarmar-studio's id/catalog-backed
# `weapon_skill_bonus`, class membership and the "Unusual" tag are supplied
# directly by the caller -- see `weapon_skill_bonus`'s docstring.
# ---------------------------------------------------------------------------


def test_weapon_skill_bonus_full_with_the_trained_weapon() -> None:
    assert combat.weapon_skill_bonus(
        3,
        skill_weapon_class="Striking",
        attack_weapon_class="Striking",
        same_weapon=True,
    ) == 3


def test_weapon_skill_bonus_half_with_another_weapon_of_the_same_class() -> None:
    # Broadsword and mace are both Striking: level 3 -> floor(3/2) = +1.
    assert combat.weapon_skill_bonus(
        3, skill_weapon_class="Striking", attack_weapon_class="Striking"
    ) == 1
    assert combat.weapon_skill_bonus(
        4, skill_weapon_class="Striking", attack_weapon_class="Striking"
    ) == 2


def test_weapon_skill_bonus_gives_nothing_across_classes() -> None:
    # Broadsword (Striking) teaches nothing about a longbow (Missile -- Bows).
    assert combat.weapon_skill_bonus(
        5, skill_weapon_class="Striking", attack_weapon_class="Missile — Bows"
    ) == 0


def test_weapon_skill_bonus_omitted_class_credits_the_skill_in_full() -> None:
    assert combat.weapon_skill_bonus(4) == 4
    assert combat.weapon_skill_bonus(4, skill_weapon_class="Striking") == 4
    assert combat.weapon_skill_bonus(4, attack_weapon_class="Striking") == 4


def test_weapon_skill_bonus_unusual_gives_full_with_itself() -> None:
    # An Unusual weapon still gives its own wielder the full bonus -- the
    # Unusual exception blocks TRANSFER, not use of the trained weapon.
    assert combat.weapon_skill_bonus(
        4,
        skill_weapon_class="Flexible / Snare",
        attack_weapon_class="Flexible / Snare",
        same_weapon=True,
        unusual=True,
    ) == 4


def test_weapon_skill_bonus_unusual_blocks_transfer_even_within_a_class() -> None:
    # Whip and net are both Flexible / Snare, but Unusual weapons are too
    # unlike one another to share training.
    assert combat.weapon_skill_bonus(
        4,
        skill_weapon_class="Flexible / Snare",
        attack_weapon_class="Flexible / Snare",
        unusual=True,
    ) == 0


def test_to_hit_bonus_applies_the_same_class_half() -> None:
    # DEX 14 (+2), skill 5 taken on a Striking weapon, swinging another
    # Striking weapon (+2 = floor(5/2)).
    assert combat.to_hit_bonus(
        effective_dexterity=14,
        skill_level=5,
        effective_strength=12,
        str_req=11,
        skill_weapon_class="Striking",
        attack_weapon_class="Striking",
    ) == 4


def test_to_hit_bonus_gives_nothing_for_a_different_class() -> None:
    assert combat.to_hit_bonus(
        effective_dexterity=14,
        skill_level=5,
        effective_strength=12,
        str_req=11,
        skill_weapon_class="Striking",
        attack_weapon_class="Missile — Bows",
    ) == 2


# ---------------------------------------------------------------------------
# FUMBLE_TABLE / fumble_table_lookup (tarmar-studio #105).
# ---------------------------------------------------------------------------


def test_fumble_table_lookup_covers_every_face() -> None:
    expected = {
        1: "off_balance",
        2: "off_balance",
        3: "off_balance",
        4: "drop_weapon",
        5: "drop_weapon",
        6: "weapon_stress",
    }
    for die, key in expected.items():
        assert combat.fumble_table_lookup(die)["key"] == key


def test_fumble_table_lookup_carries_the_die_label_and_effect() -> None:
    result = combat.fumble_table_lookup(1)
    assert result["die"] == 1
    assert result["key"] == "off_balance"
    assert "balance" in result["label"].lower()
    assert "next action" in result["effect"].lower()


def test_fumble_table_lookup_weapon_stress_names_the_second_fumble() -> None:
    assert "second fumble" in combat.fumble_table_lookup(6)["effect"].lower()


def test_fumble_table_lookup_out_of_range_die_raises() -> None:
    for die in (0, 7, -1):
        with pytest.raises(ValueError):
            combat.fumble_table_lookup(die)


def test_fumble_table_covers_one_through_six_without_gaps() -> None:
    thresholds = [threshold for threshold, _key, _label, _effect in combat.FUMBLE_TABLE]
    assert thresholds == sorted(thresholds)
    assert thresholds[-1] == combat.FUMBLE_DIE_SIDES


# ---------------------------------------------------------------------------
# §7 integration: resolve_attack's confirm_roll / fumble_roll (tarmar-studio
# #105/#101).
# ---------------------------------------------------------------------------


def test_unconfirmed_crit_doubles_the_damage_rolls() -> None:
    result = combat.resolve_attack(20, a_target_number=15, bonus=0)
    assert result["critical"]
    assert result["damage_multiplier"] == combat.CRIT_DAMAGE_ROLLS
    assert not result["severe"]
    assert not result["bleeding"]
    assert result["confirm"] is None


def test_confirm_hit_makes_it_severe() -> None:
    # 15 + 4 = 19 >= TN 17.
    result = combat.resolve_attack(20, 17, 4, confirm_roll=15)
    assert result["confirm"]["hit"]
    assert result["confirm"]["die"] == 15
    assert result["confirm"]["total"] == 19
    assert result["severe"]
    assert result["bleeding"]
    assert result["damage_multiplier"] == combat.SEVERE_CRIT_DAMAGE_ROLLS
    assert result["outcome"] == "severe critical"


def test_confirm_miss_leaves_a_plain_crit() -> None:
    # 5 + 4 = 9 < TN 17.
    result = combat.resolve_attack(20, 17, 4, confirm_roll=5)
    assert not result["confirm"]["hit"]
    assert not result["severe"]
    assert not result["bleeding"]
    assert result["damage_multiplier"] == combat.CRIT_DAMAGE_ROLLS
    assert result["outcome"] == "critical"


def test_natural_one_on_the_confirm_is_a_plain_failure_to_confirm() -> None:
    # A bonus that would otherwise clear the TN outright: the natural 1
    # still fails to confirm, and it does NOT fumble.
    result = combat.resolve_attack(20, 2, 30, confirm_roll=1)
    assert not result["confirm"]["hit"]
    assert not result["severe"]
    assert not result["fumble"]
    assert result["fumble_detail"] is None
    assert result["damage_multiplier"] == combat.CRIT_DAMAGE_ROLLS


def test_natural_twenty_on_the_confirm_always_confirms() -> None:
    result = combat.resolve_attack(20, 99, 0, confirm_roll=20)
    assert result["confirm"]["hit"]
    assert result["severe"]
    assert result["bleeding"]
    assert result["damage_multiplier"] == combat.SEVERE_CRIT_DAMAGE_ROLLS


def test_out_of_range_confirm_roll_raises() -> None:
    for confirm in (0, 21):
        with pytest.raises(ValueError):
            combat.resolve_attack(20, 15, 0, confirm_roll=confirm)


def test_confirm_at_exactly_the_target_number_confirms() -> None:
    # Roll-over is >=, so the confirm lands on the nose at TN 17: 13+4.
    on_the_nose = combat.resolve_attack(20, 17, 4, confirm_roll=13)
    assert on_the_nose["confirm"]["hit"]
    assert on_the_nose["severe"]
    # One under is a miss, and the crit stays unconfirmed.
    one_short = combat.resolve_attack(20, 17, 4, confirm_roll=12)
    assert not one_short["confirm"]["hit"]
    assert not one_short["severe"]


def test_natural_twenty_reports_the_total() -> None:
    assert combat.resolve_attack(20, 99, 7)["total"] == 27


def test_fumble_roll_attaches_the_subtable_result() -> None:
    result = combat.resolve_attack(1, 10, 5, fumble_roll=6)
    assert result["fumble"]
    assert not result["hit"]
    assert result["fumble_detail"]["key"] == "weapon_stress"
    assert result["fumble_detail"]["die"] == 6


def test_fumble_without_a_die_reports_no_subtable_result() -> None:
    result = combat.resolve_attack(1, 10, 5)
    assert result["fumble"]
    assert result["fumble_detail"] is None


def test_a_fumble_deals_no_damage() -> None:
    assert combat.resolve_attack(1, 10, 5, fumble_roll=1)["damage_multiplier"] == 0


def test_out_of_range_fumble_roll_raises() -> None:
    with pytest.raises(ValueError):
        combat.resolve_attack(1, 10, 5, fumble_roll=7)


def test_out_of_range_fumble_roll_raises_even_when_it_would_be_ignored() -> None:
    # A bad die is a caller bug whatever the attack rolled.
    for die in (12, 20):
        with pytest.raises(ValueError):
            combat.resolve_attack(die, 10, 5, fumble_roll=0)


def test_natural_one_reports_the_total() -> None:
    assert combat.resolve_attack(1, 2, 10)["total"] == 11


# ---------------------------------------------------------------------------
# The 3-arg call and its original keys survive the crit/fumble additions.
# ---------------------------------------------------------------------------


def test_positional_three_arg_call_still_works() -> None:
    assert combat.resolve_attack(12, 15, 4)["outcome"] == "hit"


def test_original_keys_are_all_still_present() -> None:
    for die in (1, 12, 20):
        result = combat.resolve_attack(die, 15, 0)
        assert {"hit", "total", "critical", "fumble", "outcome"} <= set(result)


def test_an_ordinary_hit_rolls_damage_once_and_a_miss_not_at_all() -> None:
    assert combat.resolve_attack(12, 15, 4)["damage_multiplier"] == 1
    assert combat.resolve_attack(9, 15, 4)["damage_multiplier"] == 0


def test_ordinary_rolls_ignore_crit_and_fumble_fields() -> None:
    result = combat.resolve_attack(12, 15, 4)
    assert result["confirm"] is None
    assert result["fumble_detail"] is None
    assert not result["severe"]
    assert not result["bleeding"]


def test_a_confirm_die_is_ignored_off_a_natural_twenty() -> None:
    # Only a natural 20 can be confirmed -- an ordinary hit is not a crit.
    for die, outcome in ((12, "hit"), (9, "miss"), (1, "fumble")):
        result = combat.resolve_attack(die, 15, 4, confirm_roll=20)
        assert result["outcome"] == outcome
        assert result["confirm"] is None
        assert not result["severe"]
        assert not result["bleeding"]


def test_a_fumble_die_is_ignored_off_a_natural_one() -> None:
    for die in (12, 20):
        result = combat.resolve_attack(die, 15, 4, fumble_roll=6)
        assert not result["fumble"]
        assert result["fumble_detail"] is None
