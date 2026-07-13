from modules.energy_crisis.migrations import ENERGY_CRISIS_SAVE_MIGRATIONS
from modules.energy_crisis.schema import ENERGY_CRISIS_SCHEMAS
from modules.energy_crisis.systems.energy_crisis_system import EnergyCrisisSystem
from src.shared.mod_api import feature, mod


ENERGY_CRISIS_FEATURE = feature(
    EnergyCrisisSystem,
    schemas=ENERGY_CRISIS_SCHEMAS,
    migrations=ENERGY_CRISIS_SAVE_MIGRATIONS,
    name="energy_crisis",
)


def contribute():
    return mod(features=ENERGY_CRISIS_FEATURE)
