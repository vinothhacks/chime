from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

BINDINGS_HELP = (
    ("a", "Add alarm"),
    ("e", "Edit selected"),
    ("d", "Delete selected"),
    ("space", "Toggle enabled"),
    ("t", "Test sound"),
    ("F2", "12/24 hour"),
    ("?", "Help"),
    ("q", "Quit"),
    ("s", "Snooze (when ringing)"),
    ("d", "Dismiss (when ringing)"),
)


class HelpScreen(ModalScreen[None]):
    BINDINGS = [("escape", "close", "Close"), ("q", "close", "Close")]

    def compose(self) -> ComposeResult:
        lines = ["CHIME — keyboard", ""]
        lines.extend(f"  {key:<8} {label}" for key, label in BINDINGS_HELP)
        lines.extend(
            [
                "",
                "v1 rings only while the app is running.",
                "Occurrence keys prevent duplicate rings after restart.",
            ]
        )
        with Vertical(id="help-box"):
            yield Static("\n".join(lines), id="help-text")

    def action_close(self) -> None:
        self.dismiss(None)
