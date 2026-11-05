from __future__ import annotations

import unittest

from src.client.ui.panels.military.unit_type_options import (
    DESIGN_UNIT_TYPE_OPTIONS,
    REFERENCE_UNIT_TYPE_OPTIONS,
    source_unit_type_label,
    unit_type_options_for_roles,
)


class UnitTypeOptionsTests(unittest.TestCase):
    def test_reference_types_keep_source_order_and_string_ids(self) -> None:
        self.assertEqual(
            [option.source_string_id for option in REFERENCE_UNIT_TYPE_OPTIONS],
            [
                100262, 100244, 100245, 100246, 100247,
                100248, 100249, 100250, 100251, 100252,
                100253, 100254, 100255, 100256, 100257,
                100258, 100259, 100260, 100261, 100263,
            ],
        )
        self.assertEqual(len({option.role for option in REFERENCE_UNIT_TYPE_OPTIONS}), 20)

    def test_openpower_extension_follows_native_types_without_reference_id(self) -> None:
        roles = [option.role for option in DESIGN_UNIT_TYPE_OPTIONS]
        options = unit_type_options_for_roles(roles)

        self.assertEqual([option.role for option in options], roles)
        self.assertEqual(options[-1].label, "Missile Defense (OpenPower)")
        self.assertIsNone(options[-1].source_string_id)

    def test_aliases_resolve_to_source_labels_and_order(self) -> None:
        options = unit_type_options_for_roles(["Tank", "Fighter Aircraft"])

        self.assertEqual([option.role for option in options], ["tanks", "fighters"])
        self.assertEqual(
            [option.label for option in options],
            ["Tank", "Fighter Aircraft"],
        )

    def test_unknown_openpower_roles_are_retained(self) -> None:
        options = unit_type_options_for_roles(["custom_ground_unit", "tanks"])

        self.assertEqual([option.role for option in options], ["tanks", "custom_ground_unit"])
        self.assertEqual(options[-1].label, "Custom Ground Unit")
        self.assertIsNone(options[-1].source_string_id)

    def test_rows_use_source_labels_for_known_types_and_keep_openpower_labels(self) -> None:
        self.assertEqual(source_unit_type_label("Fighter"), "Fighter Aircraft")
        self.assertEqual(source_unit_type_label("Tanks"), "Tank")
        self.assertEqual(source_unit_type_label("Estimated forces"), "Estimated forces")


if __name__ == "__main__":
    unittest.main()
