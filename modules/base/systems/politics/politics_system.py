import json
import math

import polars as pl
from modules.base.systems.world.random_event_effects import aggregate_active_effects
from modules.base.systems.politics.political_crisis_policy import (
    evaluate_crisis_transitions,
    normalize_crisis_rules,
)
from modules.base.systems.politics.political_effect_policy import (
    aggregate_political_effects_by_type,
    bounded_modifier,
)
from src.shared.system_interfaces import ISystem, SystemAccess, SystemPhase
from src.shared.system_state import SYSTEM_STATE_CACHE
from src.shared.state import GameState
from src.shared.determinism import DeterministicRuntime
from src.shared.events import (
    EventMessageCreated,
    EventNewDay,
    EventPoliticalCrisisChanged,
)

class PoliticsSystem(ISystem):
    access = SystemAccess(
        reads=frozenset(
            {
                "countries",
                "migration_signals",
                "country_laws",
                "random_event_effects",
                "political_effects",
                "country_governments",
                "government_form_rules",
                "political_crises",
                "political_history",
                "messages",
                "news_items",
            }
        ),
        writes=frozenset(
            {
                "countries",
                "migration_signals",
                "country_laws",
                "political_effects",
                "country_governments",
                "political_crises",
                "political_history",
                "messages",
                "news_items",
            }
        ),
        phase=SystemPhase.POLITICS,
    )
    runtime_state_contract = {
        "_missing_columns": SYSTEM_STATE_CACHE,
    }

    def __init__(self):
        self._missing_columns = set()

    @property
    def id(self) -> str:
        return "base.politics"

    @property
    def dependencies(self) -> list[str]:
        return ["base.population", "base.migration", "base.identity_policy"]

    def update(self, state: GameState, delta_time: float) -> None:
        self._apply_one_time_political_effects(state)

        # The engine tick counts simulation steps, so use absolute game days for weekly cadence.
        has_new_day = any(isinstance(e, EventNewDay) for e in state.events)
        if not has_new_day or state.time.is_paused:
            return

        elapsed_game_days = max(0, int(state.time.total_minutes)) // (24 * 60)
        if elapsed_game_days == 0 or elapsed_game_days % 7 != 0:
            return

        countries = state.get_table("countries")
        
        # 1. Ensure columns exist with fallbacks
        required = {
            "gvt_approval": 50.0,
            "human_dev": 0.5,
            "gvt_corruption": 0.1,
            "gvt_stability": 50.0,
            "economic_political_modifier": 1.0,
            "war_exhaustion_stability_penalty": 0.0,
        }
        for col, default in required.items():
            if col not in countries.columns:
                if col not in self._missing_columns:
                    print(f"[{self.id}] Column '{col}' not found in 'countries'. Defaulting to {default}.")
                    self._missing_columns.add(col)
                countries = countries.with_columns(pl.lit(default, dtype=pl.Float64).alias(col))
            else:
                countries = countries.with_columns(
                    pl.col(col)
                    .cast(pl.Float64, strict=False)
                    .fill_nan(float(default))
                    .fill_null(float(default))
                    .alias(col)
                )

        country_rows = countries.to_dicts()
        self._apply_migration_pressure(state, country_rows)
        self._apply_event_approval_effects(state, country_rows)
        countries = pl.DataFrame(country_rows, schema=countries.schema, strict=False)

        political_outputs = aggregate_political_effects_by_type(
            state.tables.get("political_effects"),
            int(state.time.total_minutes),
            selectors={
                ("rights", "public_rights"),
                ("stability", "stability_modifier"),
            },
        )
        political_rights = {
            country_id: value
            for (country_id, domain, effect), value in political_outputs.items()
            if (domain, effect) == ("rights", "public_rights")
        }
        if political_rights:
            rights_frame = pl.DataFrame(
                {
                    "_political_rights_country_id": list(political_rights),
                    "_political_rights_adjustment": [
                        min(25.0, max(-25.0, value * 25.0))
                        for value in political_rights.values()
                    ],
                }
            )
            countries = countries.join(
                rights_frame,
                left_on="id",
                right_on="_political_rights_country_id",
                how="left",
            ).with_columns(pl.col("_political_rights_adjustment").fill_null(0.0))
        else:
            countries = countries.with_columns(pl.lit(0.0).alias("_political_rights_adjustment"))

        political_stability = {
            country_id: value
            for (country_id, domain, effect), value in political_outputs.items()
            if (domain, effect) == ("stability", "stability_modifier")
        }
        if political_stability:
            stability_frame = pl.DataFrame(
                {
                    "_political_stability_country_id": list(political_stability),
                    "_political_stability_modifier": [
                        bounded_modifier(value) for value in political_stability.values()
                    ],
                }
            )
            countries = countries.join(
                stability_frame,
                left_on="id",
                right_on="_political_stability_country_id",
                how="left",
            ).with_columns(pl.col("_political_stability_modifier").fill_null(1.0))
        else:
            countries = countries.with_columns(pl.lit(1.0).alias("_political_stability_modifier"))

        # Existing political and economic signals remain layered over the specified baseline target.
        countries = countries.with_columns(
            (
                (
                    (
                        pl.col("gvt_approval")
                        .cast(pl.Float64, strict=False)
                        .fill_nan(50.0)
                        .fill_null(50.0)
                        + pl.col("_political_rights_adjustment")
                    )
                    .clip(0.0, 100.0)
                    * 0.7
                    + pl.col("human_dev")
                    .cast(pl.Float64, strict=False)
                    .fill_nan(0.5)
                    .fill_null(0.5)
                    * 0.3
                    - pl.col("gvt_corruption")
                    .cast(pl.Float64, strict=False)
                    .fill_nan(0.1)
                    .fill_null(0.1)
                )
                * pl.col("economic_political_modifier")
                .cast(pl.Float64, strict=False)
                .fill_null(1.0)
                .clip(0.5, 1.0)
                * pl.col("_political_stability_modifier")
                - pl.col("war_exhaustion_stability_penalty")
                .cast(pl.Float64, strict=False)
                .fill_nan(0.0)
                .fill_null(0.0)
            )
            .clip(0, 100).alias("_target_stability")
        )

        # 2. Drift towards target
        # Keep the original integer state representation after applying the specified five-percent drift.
        countries = countries.with_columns(
            (
                pl.col("gvt_stability")
                .cast(pl.Float64, strict=False)
                .fill_nan(50.0)
                .fill_null(50.0)
                + (
                    pl.col("_target_stability")
                    - pl.col("gvt_stability")
                    .cast(pl.Float64, strict=False)
                    .fill_nan(50.0)
                    .fill_null(50.0)
                )
                * 0.05
            ).cast(pl.Int64).alias("gvt_stability")
        ).drop(
            [
                "_target_stability",
                "_political_stability_modifier",
                "_political_rights_adjustment",
            ]
        )

        state.update_table("countries", countries)
        self._evaluate_crisis_thresholds(state)

    def _apply_one_time_political_effects(self, state: GameState) -> None:
        countries = state.tables.get("countries")
        effects = state.tables.get("political_effects")
        if countries is None or effects is None or countries.is_empty() or effects.is_empty():
            return

        country_rows = countries.to_dicts()
        effect_rows = effects.to_dicts()
        country_index = {
            str(row.get("id") or "").strip().upper(): row for row in country_rows
        }
        now = max(0, int(state.time.total_minutes))
        indicator_by_effect = {
            "approval_delta": "gvt_approval",
            "stability_delta": "gvt_stability",
            "corruption_delta": "gvt_corruption",
        }
        pending = sorted(
            (
                row
                for row in effect_rows
                if str(row.get("source_type") or "")
                in {"election_override", "political_crisis"}
                and str(row.get("status") or "") == "pending"
                and int(row.get("effective_at_minute") or 0) <= now
            ),
            key=lambda row: (
                int(row.get("effective_at_minute") or 0),
                str(row.get("country_id") or "").upper(),
                str(row.get("id") or ""),
            ),
        )
        if not pending:
            return

        country_changes = False
        effect_changes = False
        for effect in pending:
            country = country_index.get(str(effect.get("country_id") or "").strip().upper())
            indicator = indicator_by_effect.get(str(effect.get("effect") or ""))
            if country is None or indicator is None:
                effect["status"] = "skipped"
                effect_changes = True
                continue
            fallback = 10.0 if indicator == "gvt_corruption" else 50.0
            base = self._finite(country.get(indicator), fallback)
            if 0.0 <= base <= 1.0:
                base *= 100.0
            delta = self._finite(effect.get("value"), 0.0)
            country[indicator] = min(100.0, max(0.0, base + delta))
            effect["status"] = "applied"
            country_changes = True
            effect_changes = True

        if country_changes:
            state.update_table(
                "countries", pl.DataFrame(country_rows, schema=countries.schema, strict=False)
            )
        if effect_changes:
            state.update_table(
                "political_effects", pl.DataFrame(effect_rows, schema=effects.schema, strict=False)
            )

    def _evaluate_crisis_thresholds(self, state: GameState) -> None:
        required = {
            "countries",
            "country_governments",
            "government_form_rules",
            "political_crises",
            "political_effects",
            "political_history",
            "messages",
            "news_items",
        }
        if not required.issubset(state.tables):
            return

        countries_frame = state.tables["countries"]
        if countries_frame.is_empty() or "id" not in countries_frame.columns:
            return
        rules_by_form = {
            self._form_id(row.get("government_form_id")): normalize_crisis_rules(
                row.get("crisis_rules_json")
            )
            for row in state.tables["government_form_rules"].iter_rows(named=True)
        }
        if not any(rules_by_form.values()):
            return

        countries = countries_frame.sort("id").to_dicts()
        governments = state.tables["country_governments"].to_dicts()
        crises = state.tables["political_crises"].to_dicts()
        effects = state.tables["political_effects"].to_dicts()
        history = state.tables["political_history"].to_dicts()
        messages = state.tables["messages"].to_dicts()
        news = state.tables["news_items"].to_dicts()
        government_index = {
            self._tag(row.get("country_id")): row for row in governments
        }
        crises_by_country: dict[str, list[dict]] = {}
        for crisis in crises:
            crises_by_country.setdefault(self._tag(crisis.get("country_id")), []).append(crisis)

        now = max(0, int(state.time.total_minutes))
        runtime = DeterministicRuntime(state.determinism)
        crises_changed = effects_changed = history_changed = False
        governments_changed = messages_changed = news_changed = False

        for country in countries:
            country_id = self._tag(country.get("id"))
            government = government_index.get(country_id)
            if government is None:
                continue
            form_id = self._form_id(government.get("government_form_id"))
            rules = rules_by_form.get(form_id, ())
            if not rules:
                continue

            country_crises = crises_by_country.setdefault(country_id, [])
            transitions = evaluate_crisis_transitions(rules, country, country_crises)
            for transition in transitions:
                if transition.status == "active":
                    crisis_id = runtime.next_id(
                        "political-crisis", int(state.globals.get("tick", 0))
                    )
                    rule = transition.rule
                    support_distance = (
                        rule.threshold - transition.metric_value
                        if rule.direction == "below"
                        else transition.metric_value - rule.threshold
                    )
                    crisis = {
                        "id": crisis_id,
                        "country_id": country_id,
                        "crisis_type": rule.crisis_type,
                        "trigger": rule.rule_id,
                        "evidence_json": self._json(
                            {
                                "metric": rule.metric,
                                "value": transition.metric_value,
                                "threshold": rule.threshold,
                                "direction": rule.direction,
                                "recovery_threshold": rule.recovery_threshold,
                                "priority": rule.priority,
                            }
                        ),
                        "created_at_minute": now,
                        "deadline_at_minute": 0,
                        "resolved_at_minute": 0,
                        "support": min(1.0, max(0.0, support_distance / 100.0)),
                        "proposed_form_id": "",
                        "proposed_ruling_party_id": "",
                        "status": "active",
                        "outcome": "",
                        "reason": transition.reason,
                    }
                    crises.append(crisis)
                    country_crises.append(crisis)
                    crises_changed = True
                    for effect_name, value in (
                        ("approval_delta", rule.approval_delta),
                        ("stability_delta", rule.stability_delta),
                        ("corruption_delta", rule.corruption_delta),
                    ):
                        if value == 0.0:
                            continue
                        effects.append(
                            {
                                "id": f"{crisis_id}:{effect_name}",
                                "country_id": country_id,
                                "source_type": "political_crisis",
                                "source_id": crisis_id,
                                "domain": "crisis",
                                "effect": effect_name,
                                "value": value,
                                "effective_at_minute": now,
                                "expires_at_minute": 0,
                                "status": "pending",
                                "reason": transition.reason,
                            }
                        )
                        effects_changed = True
                    history.append(
                        {
                            "id": runtime.next_id(
                                "political-history", int(state.globals.get("tick", 0))
                            ),
                            "country_id": country_id,
                            "event_type": "political_crisis_opened",
                            "source_type": "threshold",
                            "source_id": crisis_id,
                            "game_minute": now,
                            "previous_value": "",
                            "new_value": rule.crisis_type,
                            "reason": transition.reason,
                            "result": "active",
                        }
                    )
                    history_changed = True
                    state.events.append(
                        EventPoliticalCrisisChanged(
                            country_id=country_id,
                            crisis_id=crisis_id,
                            crisis_type=rule.crisis_type,
                            status="active",
                            reason=transition.reason,
                            at_minute=now,
                        )
                    )
                    added_message, added_news = self._notify_crisis(
                        state,
                        messages,
                        news,
                        country_id,
                        crisis_id,
                        "active",
                        rule.crisis_type,
                        transition.reason,
                        now,
                    )
                    messages_changed |= added_message
                    news_changed |= added_news
                else:
                    active = next(
                        (
                            row
                            for row in country_crises
                            if self._tag(row.get("country_id")) == country_id
                            and self._text(row.get("trigger")).casefold()
                            == transition.rule.rule_id
                            and self._text(row.get("status")).casefold()
                            in {"pending", "active", "open", "escalated"}
                        ),
                        None,
                    )
                    if active is None:
                        continue
                    active.update(
                        {
                            "status": "resolved",
                            "outcome": "recovered",
                            "resolved_at_minute": now,
                            "reason": transition.reason,
                        }
                    )
                    crises_changed = True
                    history.append(
                        {
                            "id": runtime.next_id(
                                "political-history", int(state.globals.get("tick", 0))
                            ),
                            "country_id": country_id,
                            "event_type": "political_crisis_recovered",
                            "source_type": "threshold",
                            "source_id": str(active.get("id") or ""),
                            "game_minute": now,
                            "previous_value": str(active.get("crisis_type") or ""),
                            "new_value": "recovered",
                            "reason": transition.reason,
                            "result": "resolved",
                        }
                    )
                    history_changed = True
                    state.events.append(
                        EventPoliticalCrisisChanged(
                            country_id=country_id,
                            crisis_id=str(active.get("id") or ""),
                            crisis_type=str(active.get("crisis_type") or ""),
                            status="resolved",
                            reason=transition.reason,
                            at_minute=now,
                        )
                    )
                    added_message, added_news = self._notify_crisis(
                        state,
                        messages,
                        news,
                        country_id,
                        str(active.get("id") or ""),
                        "resolved",
                        str(active.get("crisis_type") or ""),
                        transition.reason,
                        now,
                    )
                    messages_changed |= added_message
                    news_changed |= added_news

            active_crises = [
                row
                for row in country_crises
                if self._text(row.get("status")).casefold()
                in {"pending", "active", "open", "escalated"}
            ]
            current_crisis_status = "none"
            if active_crises:
                priority_by_rule = {rule.rule_id: rule.priority for rule in rules}
                selected = max(
                    active_crises,
                    key=lambda row: (
                        priority_by_rule.get(self._text(row.get("trigger")).casefold(), -1),
                        self._text(row.get("crisis_type")),
                        self._text(row.get("id")),
                    ),
                )
                current_crisis_status = self._text(selected.get("crisis_type"), "none")
            if self._text(government.get("crisis_status"), "none").casefold() != current_crisis_status:
                government["crisis_status"] = current_crisis_status
                government["updated_at_minute"] = now
                governments_changed = True

        if crises_changed:
            state.update_table(
                "political_crises",
                pl.DataFrame(crises, schema=state.tables["political_crises"].schema, strict=False),
            )
        if effects_changed:
            state.update_table(
                "political_effects",
                pl.DataFrame(effects, schema=state.tables["political_effects"].schema, strict=False),
            )
        if history_changed:
            state.update_table(
                "political_history",
                pl.DataFrame(history, schema=state.tables["political_history"].schema, strict=False),
            )
        if governments_changed:
            state.update_table(
                "country_governments",
                pl.DataFrame(
                    governments,
                    schema=state.tables["country_governments"].schema,
                    strict=False,
                ),
            )
        if messages_changed:
            state.update_table(
                "messages", pl.DataFrame(messages, schema=state.tables["messages"].schema, strict=False)
            )
        if news_changed:
            state.update_table(
                "news_items", pl.DataFrame(news, schema=state.tables["news_items"].schema, strict=False)
            )

    def _notify_crisis(
        self,
        state: GameState,
        messages: list[dict],
        news: list[dict],
        country_id: str,
        crisis_id: str,
        status: str,
        crisis_type: str,
        reason: str,
        now: int,
    ) -> tuple[bool, bool]:
        outcome = "recovered" if status == "resolved" else "opened"
        subject = f"Political {crisis_type} {outcome}"
        message_id = f"{crisis_id}:{status}:message"
        news_id = f"{crisis_id}:{status}:news"
        message_changed = message_id not in {self._text(row.get("id")) for row in messages}
        news_changed = news_id not in {self._text(row.get("id")) for row in news}
        if message_changed:
            messages.append(
                {
                    "id": message_id,
                    "country_id": country_id,
                    "category": "politics",
                    "subject": subject,
                    "body": reason,
                    "is_read": False,
                    "created_at": str(state.time.date_str),
                }
            )
            state.events.append(
                EventMessageCreated(message_id=message_id, country_tag=country_id, category="politics")
            )
        if news_changed:
            news.append(
                {
                    "id": news_id,
                    "headline": subject,
                    "body": reason,
                    "category": "politics",
                    "severity": "warning" if status != "resolved" else "info",
                    "related_country_id": country_id,
                    "created_at": str(state.time.date_str),
                }
            )
        return message_changed, news_changed

    def _apply_event_approval_effects(self, state: GameState, country_rows: list[dict]) -> None:
        effects = aggregate_active_effects(
            state.tables.get("random_event_effects"),
            int(state.time.total_minutes),
            categories={"approval"},
            subject_type="country",
        )
        for country in country_rows:
            country_id = str(country.get("id") or "").strip().upper()
            effect = effects.get(("country", country_id, "approval"), 0.0)
            adjustment = min(25.0, max(-25.0, effect * 100.0))
            country["gvt_approval"] = min(
                100.0,
                max(0.0, self._finite(country.get("gvt_approval"), 50.0) + adjustment),
            )

    def _apply_migration_pressure(self, state: GameState, country_rows: list[dict]) -> None:
        signals = state.tables.get("migration_signals")
        laws = state.tables.get("country_laws")
        if signals is None or laws is None or signals.is_empty():
            return

        configured = state.globals.get("migration_politics_terms", {})
        terms = configured if isinstance(configured, dict) else {}
        approval_cost = self._finite(terms.get("approval_cost_per_pressure", 4.0), 4.0)
        service_cost = self._finite(terms.get("approval_cost_per_service_pressure", 2.0), 2.0)
        stability_cost = self._finite(terms.get("stability_cost_per_pressure", 3.0), 3.0)
        law_threshold = min(1.0, max(0.0, self._finite(terms.get("law_pressure_threshold", 0.25), 0.25)))
        countries = {
            str(row.get("id") or "").strip().upper(): row
            for row in country_rows
        }
        signal_rows = signals.to_dicts()
        changed_signals: list[dict] = []
        law_rows = laws.to_dicts()

        for signal in signal_rows:
            country_id = str(signal.get("country_id") or "").strip().upper()
            updated_at = int(signal.get("updated_at_minute") or 0)
            consumed_at = int(signal.get("politics_consumed_at_minute") or 0)
            country = countries.get(country_id)
            if country is None or updated_at <= consumed_at:
                continue

            political_pressure = self._ratio(signal.get("political_pressure"))
            service_pressure = self._ratio(signal.get("service_pressure"))
            law_pressure = self._ratio(signal.get("law_pressure"))
            country["gvt_approval"] = min(
                100.0,
                max(
                    0.0,
                    self._finite(country.get("gvt_approval"), 50.0)
                    - (political_pressure * approval_cost)
                    - (service_pressure * service_cost),
                ),
            )
            country["gvt_stability"] = min(
                100.0,
                max(
                    0.0,
                    self._finite(country.get("gvt_stability"), 50.0)
                    - (political_pressure * stability_cost),
                ),
            )
            self._upsert_migration_law(
                law_rows,
                country_id,
                law_pressure,
                law_threshold,
                int(signal.get("net_flow") or 0),
                updated_at,
            )
            signal["politics_consumed_at_minute"] = updated_at
            changed_signals.append(signal)

        if not changed_signals:
            return
        self._replace_rows(state, "migration_signals", changed_signals, "country_id")
        state.update_table(
            "country_laws",
            pl.DataFrame(law_rows, schema=laws.schema, strict=False),
        )

    def _upsert_migration_law(
        self,
        rows: list[dict],
        country_id: str,
        pressure: float,
        threshold: float,
        net_flow: int,
        updated_at: int,
    ) -> None:
        record = next(
            (
                row for row in rows
                if str(row.get("country_id") or "").strip().upper() == country_id
                and str(row.get("law_id") or "") == "migration_pressure"
            ),
            None,
        )
        if record is None:
            record = {
                "country_id": country_id,
                "law_id": "migration_pressure",
                "group_name": "Borders",
                "title": "Migration Law Pressure",
            }
            rows.append(record)
        record.update({
            "status": "Under pressure" if pressure >= threshold else "Stable",
            "value": f"{pressure:.3f}",
            "notes": (
                f"Net migration {net_flow:+d}; law-pressure signal {pressure:.3f} "
                f"at game minute {updated_at}."
            ),
        })

    def _replace_rows(self, state: GameState, table_name: str, updates: list[dict], key: str) -> None:
        frame = state.get_table(table_name)
        patch = pl.DataFrame(updates, schema=frame.schema, strict=False)
        unaffected = frame.join(patch.select(key).unique(), on=key, how="anti")
        state.update_table(
            table_name,
            pl.concat([unaffected, patch], how="vertical_relaxed").sort(key),
        )

    def _finite(self, value, default: float) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return default
        if not math.isfinite(number):
            return default
        return number

    @staticmethod
    def _text(value, default: str = "") -> str:
        return str(value if value is not None else default).strip()

    @staticmethod
    def _tag(value) -> str:
        return str(value or "").strip().upper()

    @staticmethod
    def _form_id(value) -> str:
        return " ".join(str(value or "").strip().lower().split())

    @staticmethod
    def _json(value) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def _ratio(self, value) -> float:
        return min(1.0, max(0.0, self._finite(value, 0.0)))
