from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Final
import gettext

import pycountry


DEFAULT_GEO_LANGUAGE_CODE: Final[str] = "en"
GEO_LANGUAGE_CHOICES: Final[tuple[tuple[str, str], ...]] = (
    ("en", "English"),
    ("uk", "Ukrainian"),
    ("de", "German"),
    ("fr", "French"),
    ("es", "Spanish"),
    ("pl", "Polish"),
    ("it", "Italian"),
    ("pt", "Portuguese"),
    ("tr", "Turkish"),
)
SUPPORTED_GEO_LANGUAGE_CODES: Final[tuple[str, ...]] = tuple(code for code, _ in GEO_LANGUAGE_CHOICES)


def normalize_geo_language_code(language_code: str | None) -> str:
    code = (language_code or "").strip().lower()
    if code in SUPPORTED_GEO_LANGUAGE_CODES:
        return code
    return DEFAULT_GEO_LANGUAGE_CODE


@lru_cache(maxsize=32)
def get_geo_name_resolver(language_code: str | None = None) -> "GeoNameResolver":
    return GeoNameResolver(normalize_geo_language_code(language_code))


@lru_cache(maxsize=64)
def _load_translation(domain: str, language_code: str):
    return gettext.translation(
        domain,
        pycountry.LOCALES_DIR,
        languages=[normalize_geo_language_code(language_code)],
        fallback=True,
    )


@dataclass(frozen=True, slots=True)
class GeoNameResolver:
    language_code: str = DEFAULT_GEO_LANGUAGE_CODE

    @property
    def _country_translation(self):
        return _load_translation("iso3166-1", self.language_code)

    @property
    def _region_translation(self):
        return _load_translation("iso3166-2", self.language_code)

    def country_name(self, country_code: str | None, fallback: str | None = None) -> str | None:
        if not country_code:
            return fallback

        code = country_code.strip().upper()
        country = pycountry.countries.get(alpha_3=code) or pycountry.countries.get(alpha_2=code)
        if country is None:
            return fallback

        return self._country_translation.gettext(country.name)

    def region_name(self, iso_region: str | None, fallback: str | None = None) -> str | None:
        if not iso_region:
            return fallback

        subdivision = pycountry.subdivisions.get(code=iso_region.strip().upper())
        # pycountry's Subdivisions.get may return a list of subdivisions (e.g. if querying by country_code).
        # We explicitly check for list to satisfy static type checkers that subdivision is a SubdivisionHierarchy object.
        if subdivision is None or isinstance(subdivision, list):
            return fallback

        return self._region_translation.gettext(subdivision.name)