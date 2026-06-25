# tarmar-rules

The **Tarmar d20 combat-resolution core**, extracted as a shared library so the
rules live in exactly one place. Pure Python, no dependencies, no framework.

It owns the *policy* of Tarmar combat:

- the weapon-class × armour-tier **Target Number matrix** (`MATRIX`),
- the d20 roll-over resolution (`resolve_attack`, `target_number`),
- to-hit modifiers (`dex_modifier`, `skill_bonus`, `strength_fit_penalty`,
  `to_hit_bonus`),
- crit/fumble (natural 20 / natural 1),
- the **Hybrid armour** rule (`damage_after_armour` — heavy impact weapons halve
  plate's stops),
- exact hit probabilities (`hit_probability`) for balance work.

It owns **no game data**. Each consumer tags its own weapons/armour with a
`weapon_class` (`"Piercing"`, `"Striking"`, …) and an `armour_tier`
(`"None"/"Light"/"Medium"/"Heavy"`), then calls these functions.

```python
from tarmar_rules import target_number, to_hit_bonus, resolve_attack

tn = target_number("Heavy Striking", "Heavy", shield_bonus=0, defender_dodge=1)
bonus = to_hit_bonus(effective_dexterity=12, skill_level=3,
                     effective_strength=16, str_req=14)
result = resolve_attack(die_roll=14, a_target_number=tn, bonus=bonus)
# -> {"hit": ..., "critical": ..., "fumble": ..., "outcome": ...}
```

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
