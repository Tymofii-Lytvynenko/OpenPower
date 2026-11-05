from __future__ import annotations

import unittest

from src.client.ui.components.shared.generic_message_dialog import GenericMessageDialog


class GenericMessageDialogTests(unittest.TestCase):
    def test_acknowledge_closes_dialog_before_invoking_caller(self) -> None:
        dialog = GenericMessageDialog()
        events: list[bool] = []

        dialog.show(
            "Notice",
            "Acknowledge this message.",
            on_acknowledge=lambda: events.append(dialog.is_open),
        )
        dialog.acknowledge()

        self.assertEqual(events, [False])
        self.assertFalse(dialog.is_open)

    def test_programmatic_dismiss_does_not_invoke_caller(self) -> None:
        dialog = GenericMessageDialog()
        events: list[str] = []
        dialog.show("Notice", "Dismiss without acknowledging.", on_acknowledge=lambda: events.append("ok"))

        dialog.dismiss()

        self.assertEqual(events, [])
        self.assertFalse(dialog.is_open)

    def test_acknowledgement_callback_is_consumed_once(self) -> None:
        dialog = GenericMessageDialog()
        events: list[str] = []
        dialog.show("Notice", "Acknowledge once.", on_acknowledge=lambda: events.append("ok"))

        dialog.acknowledge()
        dialog.acknowledge()

        self.assertEqual(events, ["ok"])


if __name__ == "__main__":
    unittest.main()
