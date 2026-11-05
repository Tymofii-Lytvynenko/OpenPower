"""Formatting shared by monetary values in the interface."""


def format_currency(value: float) -> str:
    return f"$ {value:,.0f}".replace(",", " ")


def format_signed_currency(value: float) -> str:
    sign = "- " if value < 0 else ""
    return f"$ {sign}{abs(value):,.0f}".replace(",", " ")
