"""Validate an invasion before diplomacy changes any authoritative tables."""
import math
from dataclasses import replace

from modules.base.systems.military.authority_policy import player_controls_country
from modules.base.systems.military.movement_access import MovementAccessPolicy
from modules.base.systems.military.movement_duration import MovementDurationPolicy
from modules.base.systems.military.movement_domains import unit_domain, has_domain_metadata, domain_route_compatible
from modules.base.systems.military.route_policy import MilitaryRoutePlanner
from modules.base.systems.military.war_policy import hostile_country_pairs
from src.shared.actions import ActionInvadeTerritory, ActionMoveUnit
from src.shared.events import EventTerritoryEntryAuthorized


def _rows(state, name):
    table = state.tables.get(name)
    return table.to_dicts() if table is not None else []


def _valid_coordinates(coordinates):
    latitude, longitude = coordinates
    return (math.isfinite(latitude) and math.isfinite(longitude)
            and -90 <= latitude <= 90 and -180 <= longitude <= 180)


def _validate_routes(state, action, selected, regions, prospective):
    planner = MilitaryRoutePlanner()
    adjacency = state.tables.get("region_adjacency")
    graph = planner.prepare(state.tables.get("regions"), adjacency)
    metadata = has_domain_metadata(regions)
    try:
        locations = MovementDurationPolicy().region_locations(state.tables["regions"])
    except (TypeError, ValueError, OverflowError):
        return "The route contains invalid geographic coordinates."
    for unit in selected:
        source = locations.get(int(unit.get("current_region_id") or 0))
        try:
            source_geo = (float(unit.get("latitude", source.latitude if source else None)),
                          float(unit.get("longitude", source.longitude if source else None)))
        except (TypeError, ValueError, OverflowError):
            return "A selected group has no valid geographic position."
        if not _valid_coordinates(source_geo):
            return "A selected group has no valid geographic position."
        domain = unit_domain(unit)
        if domain == "strategic":
            return "Strategic assets do not use conventional movement orders."

        def can_enter(region, final):
            allowed, _ = domain_route_compatible(domain, region, final, False, regions, metadata_available=metadata)
            return allowed and (prospective.can_station(region) if final else prospective.can_transit(region))

        plan = planner.plan(int(unit.get("current_region_id") or 0), action.target_region_id,
                            regions, adjacency, can_enter, prepared_graph=graph)
        if not plan.is_valid:
            return plan.rejection_reason
        if any(identity not in locations or not all(math.isfinite(v) for v in
               (locations[identity].latitude, locations[identity].longitude)) for identity in plan.region_ids[1:-1]):
            return "The route contains a region without valid coordinates."
    return None


def validate_territory_entry(state, action, war_rows):
    """Return the owning country or a rejection, without partial war/move effects."""
    if not isinstance(action.order_id, str) or not action.order_id.strip():
        return "", "The invasion order has no identity."
    if isinstance(action.target_region_id, bool) or not isinstance(action.target_region_id, int) or action.target_region_id <= 0:
        return "", "The destination region is invalid."
    if (not isinstance(action.unit_ids, (list, tuple)) or not action.unit_ids
            or any(not isinstance(key, str) or not key for key in action.unit_ids)
            or len(set(action.unit_ids)) != len(action.unit_ids)):
        return "", "Select distinct existing unit groups."
    if isinstance(action.target_latitude, bool) or isinstance(action.target_longitude, bool):
        return "", "The destination coordinates are invalid."
    try:
        coordinates = float(action.target_latitude), float(action.target_longitude)
    except (ValueError, TypeError, OverflowError):
        return "", "The destination coordinates are invalid."
    if not _valid_coordinates(coordinates):
        return "", "The destination coordinates are invalid."
    countries = {str(row.get("id")) for row in _rows(state, "countries")}
    regions = _rows(state, "regions")
    target = next((r for r in regions if r.get("id") == action.target_region_id), None)
    if target is None:
        return "", "The destination region is no longer available."
    controller = str(target.get("controller") or target.get("owner") or "").strip().upper()
    expected = str(action.expected_controller or "").strip().upper()
    if not expected or controller != expected or expected not in countries:
        return "", "The destination's military controller changed. Choose the destination again."
    units = {str(row.get("id")): row for row in _rows(state, "units")}
    selected = [units.get(key) for key in action.unit_ids]
    if any(row is None or int(row.get("strength") or 0) <= 0 for row in selected):
        return "", "One of the selected unit groups no longer exists."
    owner = str(selected[0].get("owner") or "").strip().upper()
    if (not owner or owner not in countries or owner == expected
            or any(str(row.get("owner") or "").strip().upper() != owner for row in selected)
            or not player_controls_country(state, action.player_id, owner)):
        return "", "You can authorize an invasion only with your own unit groups."
    if any(str(row.get("unit_lifecycle") or "available") != "available" for row in selected):
        return "", "All selected groups must be deployed and available."
    at_war = {next(iter(pair - {owner})) for pair in hostile_country_pairs(war_rows) if owner in pair}
    access = replace(MovementAccessPolicy().for_country(state, owner), countries_at_war=frozenset(at_war))
    if access.can_station(target) and expected not in at_war:
        return "", "Entry permission changed; issue a normal movement order instead of declaring hostilities."
    prospective = replace(access, countries_at_war=access.countries_at_war | {expected})
    route_error = _validate_routes(state, action, selected, regions, prospective)
    return ("", route_error) if route_error is not None else (owner, "")


def authorized_entry_moves(state, units=None):
    """Only a current action with matching diplomacy authorization can create moves."""
    commands = [a for a in state.current_actions if isinstance(a, ActionInvadeTerritory)]
    if not commands:
        return []
    authorizations = [e for e in state.events if isinstance(e, EventTerritoryEntryAuthorized)]
    if not authorizations:
        return []
    units_by_id = {str(row.get("id")): row for row in (units.to_dicts() if units is not None else _rows(state, "units"))}
    result = []
    for event in authorizations:
        if not any((a.order_id, a.player_id, tuple(a.unit_ids), a.target_region_id,
                    a.expected_controller, a.target_latitude, a.target_longitude) ==
                   (event.order_id, event.player_id, event.unit_ids, event.target_region_id,
                    event.target_country, event.target_latitude, event.target_longitude)
                   for a in commands if isinstance(a.unit_ids, (list, tuple))):
            continue
        selected = [units_by_id.get(identity) for identity in event.unit_ids]
        target = next((r for r in _rows(state, "regions") if r.get("id") == event.target_region_id), {})
        controller = str(target.get("controller") or target.get("owner") or "").strip().upper()
        if (controller != event.target_country.upper()
                or any(row is None or row.get("owner") != event.source_country
                       or int(row.get("strength") or 0) <= 0 for row in selected)
                or not player_controls_country(state, event.player_id, event.source_country)):
            state.journal.append_command_result({
                "tick": int(state.globals.get("tick", 0)), "player_id": event.player_id,
                "action_type": "ActionInvadeTerritory", "status": "rejected",
                "reason": "The selected units or destination changed before movement could begin.",
                "system_id": "base.military",
            })
            continue
        for identity in event.unit_ids:
            result.append(ActionMoveUnit(event.player_id, identity, event.target_region_id,
                                         event.target_latitude, event.target_longitude))
    return result
