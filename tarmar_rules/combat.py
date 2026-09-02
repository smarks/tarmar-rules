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

v0.3.0 catch-up (tarmar-rules#1): this release pulls in two rulings that had
landed in tarmar-studio's local ``characters/combat.py`` while this package
sat still (tarmar-studio issues #119, #105/#101):

* **skill_bonus is now +1 per level, uncapped** — replacing the superseded
  0/2/4/6 "Untrained/Trained/Expert/Master" ladder (tarmar-studio #119).
  :data:`SKILL_LEVEL_MAX` and its clamp are gone; a level N skill is always
  +N.
* **A weapon-skill transfer layer** (:func:`same_class_skill_bonus`,
  :func:`weapon_skill_bonus`) mirrors tarmar-studio's decision tree, but this
  package owns no weapon catalog, so the catalog lookups
  (``get_weapon_class``/``is_unusual_weapon`` by id) become plain
  caller-supplied data: a weapon-class string per side, a ``same_weapon``
  flag, and an ``unusual`` flag. See :func:`weapon_skill_bonus`'s docstring
  for the exact contract.
* **§7 is now integrated into resolve_attack** (tarmar-studio #105/#101):
  :func:`resolve_attack` grows ``confirm_roll``/``fumble_roll`` keyword
  arguments and returns ``damage_multiplier``/``severe``/``bleeding``/
  ``confirm``/``fumble_detail`` alongside the original keys. The fumble
  subtable is now also available as :data:`FUMBLE_TABLE` — ordered
  ``(threshold, key, label, effect)`` bands with the rules-page wording — and
  :func:`fumble_table_lookup` reads it.

The pre-v0.3.0 helpers (:func:`confirm_severe_crit`, the bare-string
:func:`fumble_result`, :data:`FUMBLE_OFF_BALANCE`/:data:`FUMBLE_DROP`/
:data:`FUMBLE_STRESS`, :data:`CRIT_DAMAGE_MULTIPLIER`/
:data:`SEVERE_CRIT_DAMAGE_MULTIPLIER`) stay as **deprecated aliases** — the
``melee`` consumer imports them directly and this release does not require it
to change. New code should use :func:`resolve_attack`'s integrated result and
:func:`fumble_table_lookup` instead.
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

# §7 naturals. The attack die is a d20; the fumble subtable is a d6.
DIE_FACES = 20
FUMBLE_DIE_SIDES = 6

# §7 crit knobs. A critical rolls the weapon's damage expression this many
# times and sums the results — the *dice* multiply, not the post-armour
# figure. Armour's stops come off the summed total once, so
# `damage_after_armour` needs no crit awareness.
CRIT_DAMAGE_ROLLS = 2  # natural 20: damage dice rolled twice
SEVERE_CRIT_DAMAGE_ROLLS = 3  # confirmed severe crit: triple damage

# Deprecated pre-v0.3.0 names for the two constants above. `melee` imports
# these directly; kept as aliases rather than renamed out from under it.
CRIT_DAMAGE_MULTIPLIER = CRIT_DAMAGE_ROLLS
SEVERE_CRIT_DAMAGE_MULTIPLIER = SEVERE_CRIT_DAMAGE_ROLLS

OFF_BALANCE_PENALTY = -2  # fumble 1-3: to the fumbler's next action

# Deprecated pre-v0.3.0 bare-string fumble outcomes, read by the deprecated
# `fumble_result`. `melee` compares its d6 roll's outcome against these
# directly, so they stay as-is rather than being replaced by FUMBLE_TABLE's
# richer `(threshold, key, label, effect)` bands.
FUMBLE_OFF_BALANCE = "off_balance"  # 1-3: -2 to your next action
FUMBLE_DROP = "drop"                # 4-5: drop weapon
FUMBLE_STRESS = "stress"            # 6: weapon takes stress (breaks on a second fumble)

# §7 fumble subtable, rolled on 1d6 after a natural 1. Ordered
# ``(threshold, key, label, effect)`` bands — the first band whose threshold
# the die reaches wins. Labels and effects match the wording authored in
# tarmar-studio's ``reference/content/public-rules/combat/action-options/
# attack-rolls.md``. Drop weapon carries no effect text because the rules
# print none for it. Read by :func:`fumble_table_lookup` and by
# :func:`resolve_attack`'s ``fumble_detail``.
FUMBLE_TABLE: tuple[tuple[int, str, str, str], ...] = (
    (3, "off_balance", "Off-balance", "−2 to your next action"),
    (5, "drop_weapon", "Drop weapon", ""),
    (6, "weapon_stress", "Weapon takes stress", "Breaks on a second fumble"),
)

# §3 modifier knobs.
DEX_MODIFIER_DIVISOR = 2  # floor((DEX - 10) / 2)
SKILL_BONUS_PER_LEVEL = 1  # +1 to hit per weapon-skill level, no cap (tarmar-studio #119)
SAME_CLASS_LEVEL_DIVISOR = 2  # other weapons of the same class: floor(level / 2)
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
    """To-hit bonus from weapon skill level, ``SKILL_BONUS_PER_LEVEL`` (+1) each.

    Uncapped — a level 3 skill gives +3, a level 12 skill gives +12
    (tarmar-studio #119 superseded the earlier 0/2/4/6 "Untrained/Trained/
    Expert/Master" ladder this used to implement). Negative levels give +0.
    """
    return SKILL_BONUS_PER_LEVEL * max(0, skill_level)


def same_class_skill_bonus(skill_level: int) -> int:
    """To-hit bonus the same skill gives with *another* weapon of its class.

    Half the skill level, rounded down: level 3 gives +1, level 4 gives +2.
    Negative levels give +0.
    """
    return skill_bonus(max(0, skill_level) // SAME_CLASS_LEVEL_DIVISOR)


def weapon_skill_bonus(
    skill_level: int,
    *,
    skill_weapon_class: str | None = None,
    attack_weapon_class: str | None = None,
    same_weapon: bool = False,
    unusual: bool = False,
) -> int:
    """To-hit bonus a Weapon skill gives when swinging a particular weapon.

    A Weapon skill is taken for one specific weapon. It gives the full
    :func:`skill_bonus` with that weapon, :func:`same_class_skill_bonus` with
    any other weapon of the **same class**, and nothing with a weapon of
    another class. Unusual weapons are the exception: too unlike one another
    to share training, they transfer nothing in either direction — even
    within their listed class.

    This package carries no weapon catalog, so unlike tarmar-studio's
    catalog-backed ``weapon_skill_bonus`` (which resolves a weapon id to its
    class and its "Unusual" tag), every fact this function needs is supplied
    directly by the caller:

    Args:
        skill_level: The skill's level, as in :func:`skill_bonus`.
        skill_weapon_class: The :data:`MATRIX` weapon-class string of the
            weapon the skill was trained on. ``None`` means "the skill is for
            the weapon in hand" and yields the full bonus — that is what
            plain :func:`to_hit_bonus` callers get.
        attack_weapon_class: The :data:`MATRIX` weapon-class string of the
            weapon actually being swung. ``None`` behaves the same as
            ``skill_weapon_class=None`` (full bonus).
        same_weapon: ``True`` when the weapon in hand *is* the specific
            weapon the skill was trained on (not merely the same class) —
            the caller's replacement for tarmar-studio's weapon-id equality
            check, since this package has no weapon identity of its own.
            Gives the full bonus.
        unusual: ``True`` if either weapon is caller-classified "Unusual".
            The caller determines this from its own catalog; this package
            has no notion of "Unusual" beyond the caller's say-so. Blocks
            transfer even when both classes match.

    Returns:
        The to-hit bonus this skill contributes against the attack weapon.
    """
    if skill_weapon_class is None or attack_weapon_class is None:
        return skill_bonus(skill_level)
    if same_weapon:
        return skill_bonus(skill_level)
    if unusual:
        return 0
    if skill_weapon_class == attack_weapon_class:
        return same_class_skill_bonus(skill_level)
    return 0


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
    skill_weapon_class: str | None = None,
    attack_weapon_class: str | None = None,
    same_weapon: bool = False,
    unusual: bool = False,
) -> int:
    """Total bonus added to the attacker's d20 (§2).

    Sums DEX aim, weapon skill (:func:`weapon_skill_bonus`), the
    under-strength penalty, and any situational modifier (flank/prone/range,
    re-signed for roll-over). Pass ``skill_weapon_class``/
    ``attack_weapon_class`` (and, when applicable, ``same_weapon``/
    ``unusual``) to apply the same-class transfer half-bonus instead of
    crediting the skill in full — see :func:`weapon_skill_bonus` for the
    contract.
    """
    return (
        dex_modifier(effective_dexterity)
        + weapon_skill_bonus(
            skill_level,
            skill_weapon_class=skill_weapon_class,
            attack_weapon_class=attack_weapon_class,
            same_weapon=same_weapon,
            unusual=unusual,
        )
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


def _die_hits(die_roll: int, a_target_number: int, bonus: int) -> bool:
    """Roll-over hit test, naturals included. One rule for every d20 in §2/§7.

    Kept private (rather than requiring a full :func:`resolve_attack` result
    dict) because :func:`resolve_attack` needs this same three-line check for
    both the attack die and, on a natural 20, the separate confirm die.
    """
    if die_roll == DIE_FACES:
        return True
    if die_roll == 1:
        return False
    return die_roll + bonus >= a_target_number


def resolve_attack(
    die_roll: int,
    a_target_number: int,
    bonus: int,
    *,
    confirm_roll: int | None = None,
    fumble_roll: int | None = None,
) -> dict:
    """Resolve a single attack from an already-rolled d20.

    Dice are passed in rather than rolled here so resolution stays pure and
    testable; callers roll their own dice.

    Args:
        die_roll: The attack d20 (1-20).
        a_target_number: The TN from :func:`target_number`.
        bonus: The to-hit bonus from :func:`to_hit_bonus`.
        confirm_roll: The §7 confirmation d20, consulted only on a natural 20.
            Rolled against the *same* TN with the *same* bonus. Naturals on it
            only decide confirmation: a natural 1 is a plain failure to
            confirm (no fumble), a natural 20 confirms automatically.
        fumble_roll: The §7 1d6 subtable roll, consulted only on a natural 1.
            Omit it and the fumble is reported with no subtable result.

    Returns:
        ``hit``, ``total`` (die + bonus), the ``critical``/``fumble`` flags
        and the ``outcome`` label the 3-argument form has always returned,
        plus:

        * ``damage_multiplier`` — how many times to roll the weapon's damage
          expression: 0 on a miss, 1 on a hit, :data:`CRIT_DAMAGE_ROLLS` on a
          crit, :data:`SEVERE_CRIT_DAMAGE_ROLLS` on a confirmed severe one.
          The **rolls** multiply, not the post-armour figure — armour's stops
          come off the summed total once, via unchanged
          :func:`damage_after_armour`.
        * ``severe`` / ``bleeding`` — set together on a confirmed crit. Both
          are report-only flags: nothing here persists or ticks them.
        * ``confirm`` — ``{"die", "total", "hit"}`` or None.
        * ``fumble_detail`` — :func:`fumble_table_lookup`'s dict or None. The
          boolean ``fumble`` key predates it and keeps its meaning.

    Raises:
        ValueError: if ``die_roll`` is outside 1-20, or if a supplied
            ``confirm_roll``/``fumble_roll`` is outside its face range. Both
            extra dice are range-checked whatever the attack rolled, so an
            out-of-range die is never swallowed by being irrelevant.
    """
    if not 1 <= die_roll <= DIE_FACES:
        raise ValueError(f"d20 roll out of range: {die_roll}")
    if confirm_roll is not None and not 1 <= confirm_roll <= DIE_FACES:
        raise ValueError(f"d20 confirm roll out of range: {confirm_roll}")
    # Resolved up front, not inside the natural-1 branch: a die handed in out
    # of range is a caller bug whichever face the attack rolled, and it should
    # not depend on the attack roll whether it is caught.
    fumble_detail = (
        fumble_table_lookup(fumble_roll) if fumble_roll is not None else None
    )

    result = {
        "hit": False,
        "total": die_roll + bonus,
        "critical": False,
        "fumble": False,
        "outcome": "miss",
        "damage_multiplier": 0,
        "severe": False,
        "bleeding": False,
        "confirm": None,
        "fumble_detail": None,
    }

    if die_roll == DIE_FACES:
        result.update(
            hit=True,
            critical=True,
            outcome="critical",
            damage_multiplier=CRIT_DAMAGE_ROLLS,
        )
        if confirm_roll is not None:
            confirmed = _die_hits(confirm_roll, a_target_number, bonus)
            result["confirm"] = {
                "die": confirm_roll,
                "total": confirm_roll + bonus,
                "hit": confirmed,
            }
            if confirmed:
                result.update(
                    severe=True,
                    bleeding=True,
                    outcome="severe critical",
                    damage_multiplier=SEVERE_CRIT_DAMAGE_ROLLS,
                )
        return result

    if die_roll == 1:
        result.update(fumble=True, outcome="fumble", fumble_detail=fumble_detail)
        return result

    if _die_hits(die_roll, a_target_number, bonus):
        result.update(hit=True, outcome="hit", damage_multiplier=1)
    return result


def confirm_severe_crit(
    confirm_die_roll: int, a_target_number: int, bonus: int
) -> bool:
    """§7: does a natural-20 crit upgrade to the severe result?

    .. deprecated::
        Superseded by :func:`resolve_attack`'s ``confirm_roll`` keyword,
        which resolves the same question inline and reports ``severe``/
        ``bleeding``/``confirm`` on the result. Kept because ``melee`` calls
        this directly.

    After a natural 20 the attacker immediately rolls a *second* d20 to-hit
    against the same Target Number; if that confirm roll also hits, the crit
    is severe (triple damage + bleeding, and the blow reaches Body as well as
    Fatigue). The confirm is itself a full to-hit roll, so the natural
    extremes apply: a 20 always confirms, a 1 never does.

    The confirm die is passed in rather than rolled here (same contract as
    :func:`resolve_attack`) so resolution stays pure and testable.
    """
    return resolve_attack(confirm_die_roll, a_target_number, bonus)["hit"]


def fumble_result(fumble_die_roll: int) -> str:
    """§7 fumble table: map the d6 rolled after a natural 1 to its outcome.

    .. deprecated::
        Superseded by :func:`fumble_table_lookup` (richer dict result with
        the rules-page label/effect text) and by :func:`resolve_attack`'s
        ``fumble_roll`` keyword, which attaches that dict as
        ``fumble_detail`` automatically. Kept because ``melee`` calls this
        directly and compares its result against :data:`FUMBLE_OFF_BALANCE`/
        :data:`FUMBLE_DROP`/:data:`FUMBLE_STRESS`.

    1-3 → :data:`FUMBLE_OFF_BALANCE` (:data:`OFF_BALANCE_PENALTY` to the
    fumbler's next action) · 4-5 → :data:`FUMBLE_DROP` (weapon dropped) ·
    6 → :data:`FUMBLE_STRESS` (the weapon takes stress and breaks on a second
    fumble). This table is stateless — the caller tracks the stress and the
    eventual break.

    Raises:
        ValueError: if ``fumble_die_roll`` is not a d6 face.
    """
    if not 1 <= fumble_die_roll <= FUMBLE_DIE_SIDES:
        raise ValueError(f"fumble d6 roll out of range: {fumble_die_roll}")
    if fumble_die_roll <= 3:
        return FUMBLE_OFF_BALANCE
    if fumble_die_roll <= 5:
        return FUMBLE_DROP
    return FUMBLE_STRESS


def fumble_table_lookup(die_roll: int) -> dict:
    """Look a 1d6 fumble up in :data:`FUMBLE_TABLE` (§7).

    Args:
        die_roll: The 1d6 the caller rolled after a natural 1.

    Returns:
        ``{"die", "key", "label", "effect"}``. ``effect`` is the empty string
        for the band the rules print without one (drop weapon).

    Raises:
        ValueError: if ``die_roll`` is not a d6 face — same contract as
            :func:`resolve_attack`'s d20 bound.
    """
    if not 1 <= die_roll <= FUMBLE_DIE_SIDES:
        raise ValueError(f"d6 fumble roll out of range: {die_roll}")
    band = FUMBLE_TABLE[-1]  # fallback to the last entry, mirroring lookup_table idioms
    for entry in FUMBLE_TABLE:
        if die_roll <= entry[0]:
            band = entry
            break
    _threshold, key, label, effect = band
    return {"die": die_roll, "key": key, "label": label, "effect": effect}


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
