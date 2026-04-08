import polars as pl
from src.engine.interfaces import ISystem
from src.server.state import GameState
from src.shared.events import EventRealSecond

class TradeSystem(ISystem):
    """
    Simulates international trade flows based on the pre-generated BACI trade network.
    Manages the exchange of monetary value between countries.
    """
    
    @property
    def id(self) -> str:
        return "base.trade"

    @property
    def dependencies(self) -> list[str]:
        # Trade depends on time events to trigger updates
        return ["base.time"]

    def update(self, state: GameState, delta_time: float) -> None:
        # We only run trade logic on real-second heartbeats
        real_sec_events = [e for e in state.events if isinstance(e, EventRealSecond)]
        
        for event in real_sec_events:
            if event.is_paused or event.game_seconds_passed <= 0:
                continue
            
            # Calculate what fraction of a year has passed in this tick
            # trade_network is stored in annual volumes.
            fraction_of_year = event.game_seconds_passed / (365.25 * 24 * 3600)
            
            self._process_trade_flows(state, fraction_of_year)

    def _process_trade_flows(self, state: GameState, fraction: float):
        """
        Executes monetary transfers between countries based on trade volumes.
        """
        if "trade_network" not in state.tables:
            return

        trade_net = state.get_table("trade_network")
        countries = state.get_table("countries")

        # 1. Summarize monetary transfers (exports - imports) per country
        # Transfer Value = volume * unit_price * fraction_of_year
        trade_summary = trade_net.with_columns(
            (pl.col("annual_volume") * pl.col("unit_price_usd") * fraction).alias("flow_usd")
        )

        exports = trade_summary.group_by("exporter_id").agg(
            pl.col("flow_usd").sum().alias("export_usd")
        ).rename({"exporter_id": "id"})

        imports = trade_summary.group_by("importer_id").agg(
            pl.col("flow_usd").sum().alias("import_usd")
        ).rename({"importer_id": "id"})

        # 2. Join back to the countries table
        updated_countries = countries.join(exports, on="id", how="left").join(imports, on="id", how="left").fill_null(0)

        # 3. Update money reserves
        # money_reserves = money_reserves + export_usd - import_usd
        updated_countries = updated_countries.with_columns(
            (pl.col("money_reserves") + pl.col("export_usd") - pl.col("import_usd")).alias("money_reserves")
        )

        # Drop temp columns and update state
        state.update_table("countries", updated_countries.drop(["export_usd", "import_usd"]))
