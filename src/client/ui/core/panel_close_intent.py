"""A deferred close signal shared by panels with confirmation workflows."""
from dataclasses import dataclass


@dataclass
class PanelCloseIntent:
    pending: bool = False

    def request(self):
        self.pending = True

    def consume(self):
        requested = self.pending
        self.pending = False
        return requested
