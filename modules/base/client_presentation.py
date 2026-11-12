"""Optional UI helpers exposed through the versioned public mod API."""

from __future__ import annotations

from types import MappingProxyType

from modules.base.systems.economy.unit_upkeep import unit_upkeep_by_id
from modules.base.systems.military.capability_catalog import (
    CAPABILITY_BOUNDS,
    CAPABILITY_METADATA,
    DEFAULT_ROLE_PROFILES,
    canonical_role,
)
from modules.base.systems.military.covert_operations_system import (
    CovertOperationsSystem,
)
from modules.base.systems.military.covert_policy import (
    SKILL_LEVELS,
    domestic_security_coverage,
)
from modules.base.systems.military.production_policy import (
    initial_production_eta_days,
)
from modules.base.systems.military.readiness_policy import ReadinessPolicy
from modules.base.systems.military.weapons_trade_policy import WeaponsTradePolicy
from modules.base.systems.world.authority_policy import (
    foreign_government_change_restriction,
)
from modules.base.systems.world.treaty_diplomacy import DiplomacySystem
from modules.base.systems.world.treaty_proposal_policy import (
    country_diplomacy_restriction,
    treaty_title_restriction,
)
from src.shared.mod_api import (
    CLIENT_PRESENTATION_API_VERSION,
    ClientPresentationContribution,
    ClientPresentationKeys,
)


def contribute_client_presentation() -> ClientPresentationContribution:
    """Publish only presentation helpers; simulation remains server-authoritative."""

    return ClientPresentationContribution(
        api_version=CLIENT_PRESENTATION_API_VERSION,
        values=MappingProxyType(
            {
                ClientPresentationKeys.READINESS_POLICY_FACTORY: ReadinessPolicy,
                ClientPresentationKeys.COVERT_OPERATIONS_FACTORY: CovertOperationsSystem,
                ClientPresentationKeys.COVERT_SKILL_LEVELS: SKILL_LEVELS,
                ClientPresentationKeys.DOMESTIC_SECURITY_COVERAGE: domestic_security_coverage,
                ClientPresentationKeys.WEAPONS_TRADE_POLICY_FACTORY: WeaponsTradePolicy,
                ClientPresentationKeys.UNIT_UPKEEP_BY_ID: unit_upkeep_by_id,
                ClientPresentationKeys.DEFAULT_ROLE_PROFILES: DEFAULT_ROLE_PROFILES,
                ClientPresentationKeys.CAPABILITY_BOUNDS: CAPABILITY_BOUNDS,
                ClientPresentationKeys.CAPABILITY_METADATA: CAPABILITY_METADATA,
                ClientPresentationKeys.CANONICAL_ROLE: canonical_role,
                ClientPresentationKeys.INITIAL_PRODUCTION_ETA_DAYS: initial_production_eta_days,
                ClientPresentationKeys.FOREIGN_GOVERNMENT_CHANGE_RESTRICTION:
                    foreign_government_change_restriction,
                ClientPresentationKeys.DIPLOMACY_SYSTEM_FACTORY: DiplomacySystem,
                ClientPresentationKeys.COUNTRY_DIPLOMACY_RESTRICTION:
                    country_diplomacy_restriction,
                ClientPresentationKeys.TREATY_TITLE_RESTRICTION: treaty_title_restriction,
            }
        ),
    )
