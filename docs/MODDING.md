# Modding API

The public authoring API is intentionally small. The engine still normalizes
everything into `ModContribution`, but most mods only need the `mod()` helper.

## Minimal mod

`mod.toml`:

```toml
id = "example"
name = "Example Mod"
version = "0.1.0"
api_version = 1
dependencies = ["base"]
```

`registration.py`:

```python
from src.shared.mod_api import mod

from modules.example.systems.weather import WeatherSystem


def contribute():
    return mod(WeatherSystem)
```

Pass system classes when they have zero-argument constructors. The helper
instantiates them when the mod runtime is composed.

## Configured systems

Pass a preconfigured instance or a zero-argument factory when a system needs
constructor arguments:

```python
from functools import partial

from src.shared.mod_api import mod


def contribute():
    return mod(
        WeatherSystem(config=WEATHER_CONFIG),
        partial(MigrationSystem, migration_rate=0.2),
    )
```

Factories keep construction explicit and avoid import-time registries or
decorator side effects.

## Feature packs for large mods

Use `feature()` to keep domains independently maintainable and compose them at
the module boundary:

```python
from src.shared.mod_api import feature, mod


ECONOMY = feature(
    TradeSystem,
    InternalEconomySystem,
    schemas=ECONOMY_SCHEMAS,
    migrations=ECONOMY_MIGRATIONS,
    name="economy",
)

MILITARY = feature(
    MilitarySystem,
    CombatSystem,
    schemas=MILITARY_SCHEMAS,
    name="military",
)


def contribute():
    return mod(
        TimeSystem,
        features=(ECONOMY, MILITARY),
    )
```

Feature order is preserved. The engine then resolves the final execution order
from system dependencies and phases.

## System contract

Each system declares only four things:

```python
class WeatherSystem:
    access = SystemAccess(
        reads=frozenset({"regions"}),
        writes=frozenset({"regions"}),
        handles=frozenset({ActionChangeWeatherPolicy}),
        phase=SystemPhase.RANDOM_EVENTS,
    )

    @property
    def id(self) -> str:
        return "example.weather"

    @property
    def dependencies(self) -> list[str]:
        return ["base.time"]

    def update(self, state: GameState, delta_time: float) -> None:
        ...
```

The startup validator reports duplicate IDs, missing dependencies, cycles,
invalid runtime state, schema conflicts, and unsupported actions before normal
gameplay begins.

## Data and save evolution

Schemas and migrations remain optional:

```python
def contribute():
    return mod(
        WeatherSystem,
        schemas=WEATHER_SCHEMAS,
        migrations=WEATHER_MIGRATIONS,
    )
```

Use schemas for tables owned or extended by the mod. Add one sequential save
migration whenever persisted structure changes. The same declarations work at
the root mod level or inside a feature pack.
