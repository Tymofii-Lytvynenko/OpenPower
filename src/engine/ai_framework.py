import polars as pl
from typing import Callable, List, Dict
from src.shared.actions import GameAction

# Using structural typing protocols or type aliases for functional composition.
# This avoids rigid inheritance chains and keeps the framework highly reusable.
ScorerFunc = Callable[[pl.LazyFrame], pl.LazyFrame]
ActionResolverFunc = Callable[[dict], GameAction | None]

class DeclarativeAIFramework:
    """
    A data-oriented AI orchestration engine driven by Polars.
    Separates calculation mechanisms from modular gameplay policies.
    """
    def __init__(self):
        self._scorers: List[ScorerFunc] = []
        self._action_resolvers: Dict[str, ActionResolverFunc] = {}

    def register_scorer(self, scorer: ScorerFunc) -> None:
        """
        Registers a lazy execution sub-graph modification rule.
        Order matters as expressions are applied sequentially via piping.
        """
        self._scorers.append(scorer)

    def register_action_resolver(self, action_column_id: str, resolver: ActionResolverFunc) -> None:
        """
        Binds a materialized row result to a discrete command factory.
        Triggers execution only when the mapped column evaluates to a positive utility score.
        """
        self._action_resolvers[action_column_id] = resolver

    def evaluate_and_act(self, state_lf: pl.LazyFrame) -> List[GameAction]:
        """
        Executes the compiled lazy evaluation graph natively on the Rust backend.
        Translates vector outputs to atomic action items.
        """
        if not self._scorers:
            return []

        # Functional composition pattern eliminates nested state mutations and loops.
        # Polars optimizes this chained graph into a single execution sweep.
        for scorer in self._scorers:
            state_lf = state_lf.pipe(scorer)

        # Triggering a single materialize compute pass to completely avoid GIL bottlenecks.
        decision_df = state_lf.collect()
        generated_actions: List[GameAction] = []

        # Single-pass loop over the resulting small batch of materialized actor rows.
        # Microsecond overhead on typical strategy game agent counts (e.g., 200 states).
        for row in decision_df.iter_rows(named=True):
            for column_id, resolver in self._action_resolvers.items():
                # Strict optimization: omit checking values if the flag wasn't even calculated.
                if column_id in row and row[column_id] > 0.0:
                    action = resolver(row)
                    if action:
                        generated_actions.append(action)

        return generated_actions