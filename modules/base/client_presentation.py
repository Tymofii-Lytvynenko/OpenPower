"""Optional UI helpers exposed through the versioned public mod API."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from modules.base.systems.economy.unit_upkeep import unit_upkeep_by_id
from modules.base.systems.military.capability_catalog import (
    CAPABILITY_BOUNDS,
    CAPABILITY_METADATA,
    DEFAULT_ROLE_PROFILES,
    canonical_role,
)
from modules.base.systems.military.covert_operations_system import (
    CovertCellCreationQuote as _CovertCellCreationQuote,
)
from modules.base.systems.military.covert_operations_system import (
    CovertOperationsSystem as _CovertOperationsSystem,
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
from modules.base.systems.world.treaty_diplomacy import (
    DiplomacySystem as _DiplomacySystem,
)
from modules.base.systems.world.treaty_proposal_policy import (
    country_diplomacy_restriction,
    treaty_title_restriction,
)
from src.shared.mod_api import (
    CLIENT_PRESENTATION_API_VERSION,
    ClientPresentationContribution,
    ClientPresentationKeys,
)


class CovertCreationQuoteService:
    """Expose the cell-creation quote needed by the client UI."""

    def __init__(self) -> None:
        self._operations = _CovertOperationsSystem()

    def quote_cell_creation(
        self,
        state: Any,
        owner_tag: str,
        target_tag: str,
        training_level: str = "Recruit",
    ) -> _CovertCellCreationQuote:
        return self._operations.quote_cell_creation(
            state, owner_tag, target_tag, training_level
        )


class TreatyEligibilityQueryService:
    """Expose treaty eligibility queries without exposing the simulation system."""

    def __init__(self) -> None:
        self._diplomacy = _DiplomacySystem()

    def eligible_treaty_countries(
        self,
        state: Any,
        treaty: Mapping[str, Any],
    ) -> frozenset[str]:
        return self._diplomacy.eligible_treaty_countries(state, treaty)

    def ineligible_treaty_members(
        self,
        state: Any,
        treaty: Mapping[str, Any],
    ) -> frozenset[str]:
        return self._diplomacy.ineligible_treaty_members(state, treaty)


def contribute_client_presentation() -> ClientPresentationContribution:
    """Publish only presentation helpers; simulation remains server-authoritative."""

    return ClientPresentationContribution(
        api_version=CLIENT_PRESENTATION_API_VERSION,
        values=MappingProxyType(
            {
                ClientPresentationKeys.READINESS_POLICY_FACTORY: ReadinessPolicy,
                ClientPresentationKeys.COVERT_CREATION_QUOTE_SERVICE_FACTORY:
                    CovertCreationQuoteService,
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
                ClientPresentationKeys.TREATY_ELIGIBILITY_QUERY_SERVICE_FACTORY:
                    TreatyEligibilityQueryService,
                ClientPresentationKeys.COUNTRY_DIPLOMACY_RESTRICTION:
                    country_diplomacy_restriction,
                ClientPresentationKeys.TREATY_TITLE_RESTRICTION: treaty_title_restriction,
            }
        ),
    )
