import json
import polars as pl
from typing import Any

from modules.base.systems.military.capability_catalog import get_role_profile, project_capabilities
from modules.base.systems.military.unit_catalog import MILITARY_UNIT_TYPES
from src.shared.system_interfaces import ISystem, SystemAccess, SystemPhase
from src.shared.state import GameState

class BootstrapSystem(ISystem):
    """
    Seeds initial gameplay content (laws, default objective tracks, designs)
    inside the base module. This separates content policy from the server engine.
    """

    access = SystemAccess(
        reads=frozenset({'countries', 'regions', 'countries_treaties', 'countries_wars', 'migration_policies', 'country_identity_distribution', 'country_identity_groups'}),
        writes=frozenset({'country_governments', 'country_laws', 'migration_policies', 'country_identity_groups', 'messages', 'news_items', 'objectives', 'research_tracks', 'unit_designs', 'strategic_weapons'}),
        phase=SystemPhase.BOOTSTRAP,
    )

    @property
    def id(self) -> str:
        return "base.bootstrap"

    @property
    def dependencies(self) -> list[str]:
        # Needs base.time to run first so game date is initialized
        return ["base.time"]

    def update(self, state: GameState, delta_time: float) -> None:
        # Check if country governments are seeded yet. If not, seed all tables.
        govs = state.get_table("country_governments")
        if govs is None or govs.is_empty():
            self._seed_all_content(state)
        self._seed_migration_policies(state)
        self._seed_country_identity_groups(state)

    def _seed_country_identity_groups(self, state: GameState) -> None:
        if state.globals.get("country_identity_groups_seeded"):
            return
        definitions = state.tables.get("country_identity_distribution")
        groups = state.tables.get("country_identity_groups")
        if definitions is None or groups is None or definitions.is_empty():
            return

        known = {
            (
                self._tag(row.get("country_id")),
                str(row.get("identity_type") or "").strip().lower(),
                str(row.get("identity_id") or "").strip().lower(),
            )
            for row in groups.iter_rows(named=True)
        }
        now = max(0, int(state.time.total_minutes))
        additions = []
        for row in definitions.iter_rows(named=True):
            key = (
                self._tag(row.get("country_id")),
                str(row.get("identity_type") or "").strip().lower(),
                str(row.get("identity_id") or "").strip().lower(),
            )
            if not all(key) or key in known:
                continue
            additions.append(
                {
                    **row,
                    "legal_status": "legal",
                    "last_policy_change_minute": 0,
                    "last_updated_minute": now,
                }
            )
        if additions:
            state.update_table(
                "country_identity_groups",
                pl.concat(
                    [groups, pl.DataFrame(additions, schema=groups.schema, strict=False)],
                    how="vertical_relaxed",
                ),
            )
        state.globals["country_identity_groups_seeded"] = True

    def _seed_migration_policies(self, state: GameState) -> None:
        countries = state.tables.get("countries")
        policies = state.tables.get("migration_policies")
        if countries is None or policies is None or countries.is_empty():
            return
        known = {
            self._tag(country_id)
            for country_id in policies.get_column("country_id").to_list()
        }
        records = [
            {
                "country_id": country_id,
                "migration_policy": "managed",
                "border_policy": "managed",
                "entry_rate": 0.5,
                "exit_rate": 0.5,
                "asylum_rate": 0.25,
                "family_reunification_rate": 0.5,
                "skilled_worker_preference": 0.0,
                "enforcement_strength": 0.5,
                "effective_at_minute": 0,
                "updated_at_minute": max(0, int(state.time.total_minutes)),
                "source": "default",
            }
            for country_id in sorted(
                {self._tag(value) for value in countries["id"].to_list()}
            )
            if country_id and country_id not in known
        ]
        if records:
            additions = pl.DataFrame(records, schema=policies.schema, strict=False)
            state.update_table(
                "migration_policies",
                pl.concat([policies, additions], how="vertical_relaxed"),
            )

    def _seed_all_content(self, state: GameState) -> None:
        print("[BootstrapSystem] Seeding gameplay content tables...")
        
        gov_rows = self._build_country_governments(state)
        if gov_rows:
            # We preserve standard schema by creating a Polars dataframe
            state.update_table("country_governments", pl.DataFrame(gov_rows))
        
        law_rows = self._build_country_laws(state)
        if law_rows:
            state.update_table("country_laws", pl.DataFrame(law_rows))
            
        msg_rows = self._build_messages(state)
        if msg_rows:
            state.update_table("messages", pl.DataFrame(msg_rows))
            
        news_rows = self._build_news_items(state)
        if news_rows:
            state.update_table("news_items", pl.DataFrame(news_rows))
            
        obj_rows = self._build_objectives(state)
        if obj_rows:
            state.update_table("objectives", pl.DataFrame(obj_rows))
            
        track_rows = self._build_research_tracks(state)
        if track_rows:
            state.update_table("research_tracks", pl.DataFrame(track_rows))
            
        design_rows = self._build_unit_designs(state)
        if design_rows:
            state.update_table("unit_designs", pl.DataFrame(design_rows))
            
        wpn_rows = self._build_strategic_weapons(state)
        if wpn_rows:
            weapon_table = state.tables.get("strategic_weapons")
            state.update_table(
                "strategic_weapons",
                pl.DataFrame(wpn_rows, schema=None if weapon_table is None else weapon_table.schema, strict=False),
            )

    def _build_country_governments(self, state: GameState) -> list[dict[str, Any]]:
        countries = state.tables.get("countries")
        if countries is None or countries.is_empty() or "id" not in countries.columns:
            return []

        home_regions = self._home_regions_by_country(state.tables.get("regions"))
        rows: list[dict[str, Any]] = []
        for row in countries.iter_rows(named=True):
            country_id = str(row["id"])
            approval = self._as_ratio(row.get("gvt_approval"), 0.5)
            stability = self._as_ratio(row.get("gvt_stability"), 0.5)
            corruption = self._as_ratio(row.get("gvt_corruption"), 0.4)
            development = self._as_ratio(row.get("human_dev"), 0.45)

            government_type = self._classify_government(approval, stability, corruption, development)
            rows.append(
                {
                    "country_id": country_id,
                    "government_type": government_type,
                    "capital_region_id": home_regions.get(country_id, 0),
                    "next_election": self._estimate_next_election(approval, development),
                    "martial_law": stability < 0.30,
                    "election_risk": max(0.0, min(1.0, 1.0 - ((approval * 0.55) + (stability * 0.45)))),
                    "ideology_balance": max(
                        0.0,
                        min(1.0, 1.0 - (self._as_ratio(row.get("global_tax_rate"), 0.2) * 1.5)),
                    ),
                }
            )

        return rows

    def _build_country_laws(self, state: GameState) -> list[dict[str, Any]]:
        countries = state.tables.get("countries")
        if countries is None or countries.is_empty() or "id" not in countries.columns:
            return []

        rows: list[dict[str, Any]] = []
        for row in countries.iter_rows(named=True):
            country_id = str(row["id"])
            approval = self._as_ratio(row.get("gvt_approval"), 0.5)
            stability = self._as_ratio(row.get("gvt_stability"), 0.5)
            corruption = self._as_ratio(row.get("gvt_corruption"), 0.4)
            development = self._as_ratio(row.get("human_dev"), 0.45)
            reserves = float(row.get("money_reserves") or 0.0)

            law_rows = (
                {
                    "law_id": "religion_policy",
                    "group_name": "Society",
                    "title": "Religion Policy",
                    "status": "Open recognition" if development >= 0.45 else "State supervision",
                    "value": "Plural framework" if approval >= 0.45 else "Monitored practice",
                    "notes": "Derived from development and approval indicators.",
                },
                {
                    "law_id": "language_policy",
                    "group_name": "Society",
                    "title": "Language Policy",
                    "status": "Multilingual support" if development >= 0.60 else "Single official channel",
                    "value": "Minority protection" if development >= 0.60 else "State-first administration",
                    "notes": "Derived from development indicators.",
                },
                {
                    "law_id": "party_system",
                    "group_name": "Parties",
                    "title": "Party Registration",
                    "status": "Open registration" if approval >= 0.50 else "Restricted funding",
                    "value": "Competitive" if approval >= 0.50 else "Managed competition",
                    "notes": "Derived from approval levels.",
                },
                {
                    "law_id": "civil_rights",
                    "group_name": "Rights",
                    "title": "Civil Rights",
                    "status": "Protected" if corruption <= 0.35 else "Under pressure",
                    "value": "Judicial review" if corruption <= 0.35 else "Administrative controls",
                    "notes": "Derived from corruption indicators.",
                },
                {
                    "law_id": "migration_policy",
                    "group_name": "Borders",
                    "title": "Migration Policy",
                    "status": "Managed entry" if reserves >= 0 else "Emergency limits",
                    "value": "Quota system" if reserves >= 0 else "Tight restrictions",
                    "notes": "Derived from reserve balance.",
                },
                {
                    "law_id": "border_policy",
                    "group_name": "Borders",
                    "title": "Border Policy",
                    "status": "Screened access" if stability >= 0.35 else "Security lockdown",
                    "value": "Trade corridors open" if stability >= 0.35 else "Priority checkpoints",
                    "notes": "Derived from stability indicators.",
                },
            )

            for law in law_rows:
                rows.append({"country_id": country_id, **law})

        return rows

    def _build_messages(self, state: GameState) -> list[dict[str, Any]]:
        countries = state.tables.get("countries")
        if countries is None or countries.is_empty() or "id" not in countries.columns:
            return []

        created_at = state.time.date_str
        rows: list[dict[str, Any]] = []
        for row in countries.iter_rows(named=True):
            country_id = str(row["id"])
            if not self._is_playable(row):
                continue

            rows.append(
                {
                    "id": f"brief-{country_id}",
                    "country_id": country_id,
                    "category": "briefing",
                    "subject": "Cabinet brief ready",
                    "body": "The current cabinet packet includes diplomacy, budget, and force posture summaries.",
                    "is_read": False,
                    "created_at": created_at,
                }
            )

        return rows

    def _build_news_items(self, state: GameState) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        created_at = state.time.date_str

        treaties = state.tables.get("countries_treaties")
        if treaties is not None and not treaties.is_empty():
            for row in treaties.head(8).iter_rows(named=True):
                treaty_name = str(row.get("name") or row.get("id") or "Treaty")
                rows.append(
                    {
                        "id": f"news-treaty-{row.get('id', treaty_name)}",
                        "headline": f"{treaty_name} remains active",
                        "body": "Member coordination and obligations remain in force.",
                        "category": "diplomacy",
                        "severity": "info",
                        "related_country_id": "",
                        "created_at": created_at,
                    }
                )

        wars = state.tables.get("countries_wars")
        if wars is not None and not wars.is_empty():
            for index, row in enumerate(wars.head(8).iter_rows(named=True), start=1):
                attacker = ", ".join(self._normalize_side(row.get("side_a"))) or "Unknown"
                defender = ", ".join(self._normalize_side(row.get("side_b"))) or "Unknown"
                rows.append(
                    {
                        "id": f"news-war-{index}",
                        "headline": f"Conflict watch: {attacker} vs {defender}",
                        "body": "The operations board is monitoring active military commitments.",
                        "category": "war",
                        "severity": "warning",
                        "related_country_id": "",
                        "created_at": created_at,
                    }
                )

        if not rows:
            rows.append(
                {
                    "id": "news-bootstrap",
                    "headline": "Operations center online",
                    "body": "Live news feeds are ready for new world events.",
                    "category": "system",
                    "severity": "info",
                    "related_country_id": "",
                    "created_at": created_at,
                }
            )

        return rows

    def _build_objectives(self, state: GameState) -> list[dict[str, Any]]:
        countries = state.tables.get("countries")
        if countries is None or countries.is_empty() or "id" not in countries.columns:
            return []

        rows: list[dict[str, Any]] = []
        for row in countries.iter_rows(named=True):
            if not self._is_playable(row):
                continue

            country_id = str(row["id"])
            stability = self._as_ratio(row.get("gvt_stability"), 0.5)
            reserves = float(row.get("money_reserves") or 0.0)
            readiness = min(1.0, max(0.0, float(row.get("military_count") or 0.0) / 500_000.0))

            rows.extend(
                [
                    {
                        "id": f"obj-stability-{country_id}",
                        "country_id": country_id,
                        "title": "Steady government approval",
                        "description": "Keep government stability above fifty percent.",
                        "status": "active",
                        "progress": stability,
                    },
                    {
                        "id": f"obj-reserves-{country_id}",
                        "country_id": country_id,
                        "title": "Maintain positive reserves",
                        "description": "Avoid a negative reserve balance while funding core services.",
                        "status": "active",
                        "progress": 1.0 if reserves >= 0 else 0.0,
                    },
                    {
                        "id": f"obj-readiness-{country_id}",
                        "country_id": country_id,
                        "title": "Keep armed forces ready",
                        "description": "Sustain a deployable force posture and avoid hollow readiness.",
                        "status": "active",
                        "progress": readiness,
                    },
                ]
            )

        return rows

    def _build_research_tracks(self, state: GameState) -> list[dict[str, Any]]:
        countries = state.tables.get("countries")
        if countries is None or countries.is_empty() or "id" not in countries.columns:
            return []

        rows: list[dict[str, Any]] = []
        branches = (
            ("ground", "Land modernization"),
            ("air", "Air superiority"),
            ("naval", "Fleet sustainment"),
            ("strategic", "Strategic deterrence"),
            ("strategic_program", "Strategic program"),
            ("strategic_weapons", "Strategic weapons"),
            ("strategic_defense", "Missile defense"),
        )
        for row in countries.iter_rows(named=True):
            country_id = str(row["id"])
            if not self._is_playable(row):
                continue

            research_ratio = self._as_ratio(row.get("budget_research_ratio"), 0.12)
            development = self._as_ratio(row.get("human_dev"), 0.45)
            for index, (branch, focus) in enumerate(branches, start=1):
                rows.append(
                    {
                        "id": f"{country_id}-{branch}",
                        "country_id": country_id,
                        "branch": branch,
                        "funding_ratio": research_ratio,
                        "progress": max(0.05, min(0.95, development * (0.60 + (index * 0.05)))),
                        "priority": index,
                        "focus": focus,
                    }
                )

        return rows

    def _build_unit_designs(self, state: GameState) -> list[dict[str, Any]]:
        countries = state.tables.get("countries")
        if countries is None or countries.is_empty() or "id" not in countries.columns:
            return []

        rows: list[dict[str, Any]] = []
        for row in countries.iter_rows(named=True):
            country_id = str(row["id"])
            if not self._is_playable(row):
                continue

            technology = self._military_technology_index(row)
            for unit_type in MILITARY_UNIT_TYPES:
                profile = get_role_profile(unit_type.role)
                capabilities = self._country_unit_capabilities(profile, technology)
                gun_damage = capabilities.get("gun_damage", 0.0)
                missile_damage = capabilities.get("missile_damage", 0.0)
                firepower = min(1.0, max(0.0, ((gun_damage + missile_damage) / 20.0) + (technology * 0.25)))
                quantity = max(0, int(row.get(unit_type.quantity_column) or 0))
                rows.append(
                    {
                        "id": f"{country_id}-{unit_type.role}-2001",
                        "country_id": country_id,
                        "branch": profile.domain,
                        "class_name": unit_type.display_name,
                        "display_name": f"{country_id} {unit_type.display_name} 2001",
                        "starting_quantity_2001": quantity,
                        "quality": technology,
                        "cost": unit_type.unit_cost * (0.85 + (technology * 0.30)),
                        "maintenance_cost": unit_type.maintenance_cost,
                        "speed": capabilities.get("speed", 0.0),
                        "firepower": firepower,
                        "domain": profile.domain,
                        "capabilities_json": json.dumps(capabilities, sort_keys=True, separators=(",", ":")),
                        "valid_targets_json": json.dumps(list(profile.valid_targets), separators=(",", ":")),
                        "vulnerabilities_json": json.dumps(list(profile.vulnerabilities), separators=(",", ":")),
                        "research_level": max(0, min(10, int(round(technology * 10.0)))),
                        "research_requirements_json": "{}",
                    }
                )

        return rows

    def _military_technology_index(self, row: dict[str, Any]) -> float:
        development = self._as_ratio(row.get("human_dev"), 0.45)
        research = self._as_ratio(row.get("budget_research_ratio"), 0.10)
        return max(0.35, min(0.98, 0.45 + (development * 0.50) + (research * 0.10)))

    def _country_unit_capabilities(
        self,
        profile: Any,
        technology: float,
    ) -> dict[str, float]:
        base = project_capabilities(profile)
        multipliers = {
            "speed": 0.75 + (technology * 0.25),
            "maneuverability": 0.70 + (technology * 0.30),
            "sensors": 0.55 + (technology * 0.45),
            "gun_range": 0.75 + (technology * 0.25),
            "gun_precision": 0.50 + (technology * 0.50),
            "gun_damage": 0.70 + (technology * 0.30),
            "missile_payload": 0.80 + (technology * 0.20),
            "missile_range": 0.65 + (technology * 0.35),
            "missile_precision": 0.50 + (technology * 0.50),
            "missile_damage": 0.70 + (technology * 0.30),
            "stealth": 0.70 + (technology * 0.30),
            "countermeasures": 0.50 + (technology * 0.50),
            "armor": 0.80 + (technology * 0.20),
        }
        return {
            key: value * multipliers.get(key, 1.0)
            for key, value in base.items()
        }

    def _build_strategic_weapons(self, state: GameState) -> list[dict[str, Any]]:
        countries = state.tables.get("countries")
        if countries is None or countries.is_empty() or "id" not in countries.columns:
            return []

        rows: list[dict[str, Any]] = []
        profiles = self._strategic_weapon_profiles(state)
        weapon_classes = ("icbm", "slbm") if "slbm" in profiles else ("icbm",)
        for row in countries.iter_rows(named=True):
            country_id = str(row["id"])
            if not self._is_playable(row):
                continue

            land_missiles = max(0, int(row.get("military_strategic_missiles_quantity_2001") or 0))
            missile_submarines = max(
                0,
                int(row.get("military_ballistic_missile_submarines_quantity_2001") or 0),
            )

            for weapon_class in weapon_classes:
                profile = profiles.get(weapon_class, {})
                if profile.get("enabled") is False:
                    continue

                default_quantity = land_missiles if weapon_class == "icbm" else missile_submarines * 16
                initial_quantity = max(0, int(profile.get("initial_quantity", default_quantity)))
                default_ready = int(initial_quantity * 0.75)
                initial_ready = min(initial_quantity, max(0, int(profile.get("initial_ready", default_ready))))
                payload_cap = min(10, max(1, int(profile.get("max_payload_level", 1) or 1)))
                payload_level = min(payload_cap, max(1, int(profile.get("payload_level", 1) or 1)))
                rows.append({
                    "id": f"{country_id}-strategic" if weapon_class == "icbm" else f"{country_id}-{weapon_class}",
                    "country_id": country_id,
                    "weapon_type": profile.get(
                        "weapon_type",
                        "Ballistic missiles" if weapon_class == "icbm" else "Submarine-launched ballistic missiles",
                    ),
                    "quantity": initial_quantity,
                    "ready": initial_ready,
                    "defense_rating": max(0.05, min(0.95, self._as_ratio(row.get("budget_research_ratio"), 0.1) * 1.8)),
                    "weapon_class": weapon_class,
                    "range_km": max(0.0, float(profile.get("range_km", 12000.0 if weapon_class == "icbm" else 0.0))),
                    "payload_level": payload_level,
                    "max_payload_level": payload_cap,
                    "required_research_level": max(1, int(profile.get("required_research_level", 1) or 1)),
                    "operational": bool(profile.get("operational", True)),
                    "launch_cost": max(0.0, float(profile.get("launch_cost", 0.0) or 0.0)),
                    "flight_minutes": max(0, int(profile.get("flight_minutes", 0) or 0)),
                    "readiness_minutes": max(0, int(profile.get("readiness_minutes", 60) or 0)),
                    "production_cost": max(0.0, float(profile.get("production_cost", 0.0) or 0.0)),
                    "production_minutes": max(0, int(profile.get("production_minutes", 0) or 0)),
                })

        return rows

    def _strategic_weapon_profiles(self, state: GameState) -> dict[str, dict[str, Any]]:
        profiles: dict[str, dict[str, Any]] = {}
        for setting in ("strategic_weapon_production_profiles", "strategic_weapon_profiles"):
            configured = state.globals.get(setting, {})
            if not isinstance(configured, dict):
                continue
            for weapon_class, profile in configured.items():
                normalized_class = str(weapon_class).strip().lower()
                if normalized_class not in {"icbm", "slbm"} or not isinstance(profile, dict):
                    continue
                profiles.setdefault(normalized_class, {}).update(profile)
        return profiles

    def _home_regions_by_country(self, regions: pl.DataFrame | None) -> dict[str, int]:
        if regions is None or regions.is_empty() or not {"id", "owner"}.issubset(set(regions.columns)):
            return {}

        score_columns = [column for column in ("pop_15_64", "area_km2") if column in regions.columns]
        selected: dict[str, tuple[int, float]] = {}
        for row in regions.iter_rows(named=True):
            owner = row.get("owner")
            region_id = row.get("id")
            if not owner or owner == "None" or region_id is None:
                continue

            score = 0.0
            for column in score_columns:
                score += float(row.get(column) or 0.0)

            owner_key = str(owner)
            current = selected.get(owner_key)
            if current is None or score > current[1]:
                selected[owner_key] = (int(region_id), score)

        return {country_id: region_id for country_id, (region_id, _) in selected.items()}

    def _classify_government(self, approval: float, stability: float, corruption: float, development: float) -> str:
        if stability < 0.25:
            return "Emergency administration"
        if development >= 0.75 and approval >= 0.45:
            return "Multi-party democracy"
        if corruption >= 0.60 and approval < 0.40:
            return "Military-led state"
        if development >= 0.55:
            return "Centralized republic"
        return "Transitional republic"

    def _estimate_next_election(self, approval: float, development: float) -> str:
        year = 2002 + int(round((approval + development) * 3))
        return f"{year:04d}-06-01"

    def _normalize_side(self, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, list):
            return tuple(str(tag) for tag in value if tag is not None)
        if isinstance(value, tuple):
            return tuple(str(tag) for tag in value if tag is not None)
        if isinstance(value, str):
            return tuple(tag.strip() for tag in value.split(",") if tag.strip())
        return ()

    def _as_ratio(self, value: Any, default: float) -> float:
        if value is None:
            return default
        number = float(value)
        if number > 1.0:
            number /= 100.0
        return max(0.0, min(1.0, number))

    def _tag(self, value: Any) -> str:
        return str(value or "").strip().upper()

    def _is_playable(self, row: dict[str, Any]) -> bool:
        value = row.get("is_playable", True)
        if isinstance(value, bool):
            return value
        return str(value).lower() == "true"
