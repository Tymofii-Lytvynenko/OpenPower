from collections.abc import MutableSet


class MissingColumnWarningRegistry:
    """Emit each missing economy-column warning once per system instance."""

    def __init__(
        self,
        system_id: str,
        seen_columns: MutableSet[str] | None = None,
    ) -> None:
        self._system_id = system_id
        self._seen_columns = seen_columns if seen_columns is not None else set()

    @property
    def seen_columns(self) -> MutableSet[str]:
        return self._seen_columns

    @seen_columns.setter
    def seen_columns(self, value: MutableSet[str]) -> None:
        self._seen_columns = value

    def report_missing(self, column: str, default: bool | float) -> None:
        if column in self._seen_columns:
            return
        print(
            f"[{self._system_id}] Column '{column}' not found in 'domestic_production'. "
            f"Defaulting to {default}."
        )
        self._seen_columns.add(column)
