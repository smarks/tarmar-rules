# tarmar-rules

The **Tarmar d20 combat-resolution core**, extracted as a shared library so the
rules live in exactly one place. Pure Python, no dependencies, no framework.

It owns the *policy* of Tarmar combat:

- the weapon-class × armour-tier **Target Number matrix** (`MATRIX`),
- the d20 roll-over resolution, with the §7 crit/fumble outcomes integrated
  in (`resolve_attack`, `target_number`),
- to-hit modifiers (`dex_modifier`, `skill_bonus`, `strength_fit_penalty`,
  `to_hit_bonus`),
- the **weapon-skill transfer layer** — a Weapon skill's full bonus with its
  own weapon, half with another weapon of the same class, none across
  classes or through an Unusual weapon (`same_class_skill_bonus`,
  `weapon_skill_bonus`),
- crit/fumble (natural 20 / natural 1), including the confirmed-severe-crit
  upgrade and the §7 fumble subtable (`FUMBLE_TABLE`, `fumble_table_lookup`),
- the **Hybrid armour** rule (`damage_after_armour` — heavy impact weapons halve
  plate's stops),
- exact hit probabilities (`hit_probability`) for balance work.

It owns **no game data**. Each consumer tags its own weapons/armour with a
`weapon_class` (`"Piercing"`, `"Striking"`, …) and an `armour_tier`
(`"None"/"Light"/"Medium"/"Heavy"`), then calls these functions. The package
also owns no weapon *catalog* — `weapon_skill_bonus` decides the transfer
from weapon-class strings and flags the caller supplies directly (see its
docstring), rather than looking a weapon id up anywhere.

```python
from tarmar_rules import target_number, to_hit_bonus, resolve_attack

tn = target_number("Heavy Striking", "Heavy", shield_bonus=0, defender_dodge=1)
bonus = to_hit_bonus(effective_dexterity=12, skill_level=3,
                     effective_strength=16, str_req=14)
result = resolve_attack(die_roll=14, a_target_number=tn, bonus=bonus,
                        confirm_roll=9, fumble_roll=None)
# -> {"hit": ..., "critical": ..., "fumble": ..., "outcome": ...,
#     "damage_multiplier": ..., "severe": ..., "bleeding": ...,
#     "confirm": ..., "fumble_detail": ...}
```

A handful of pre-v0.3.0 names (`confirm_severe_crit`, the bare-string
`fumble_result`, `FUMBLE_OFF_BALANCE`/`FUMBLE_DROP`/`FUMBLE_STRESS`,
`CRIT_DAMAGE_MULTIPLIER`/`SEVERE_CRIT_DAMAGE_MULTIPLIER`) stay in place as
deprecated aliases for `melee`, which still imports them directly. New code
should read `resolve_attack`'s integrated result instead.

## Consumers

- **tarmar-studio** — the Django second-brain app's GM combat.
- **melee** — the standalone *Fantasy Trip: Melee* game, as its "Tarmar rules"
  profile (alongside classic Melee).

Design rationale and the locked hit-chance surface live in tarmar-studio's
`reference/content/proposals/d20-combat-resolution-spec.md`.

## Develop

```bash
pip install -e '.[test]'
pytest
```
