from dataclasses import dataclass, field
from typing import Any, Protocol, Dict, List

class Renderable(Protocol):
    def render(self, state: Any, **kwargs) -> bool: ...

@dataclass
class PanelEntry:
    id: str
    instance: Renderable
    visible: bool
    icon: str = ""
    color: tuple = (1,1,1,1)

class PanelManager:
    """
    Manages the lifecycle and visibility of UI panels via Composition.
    """
    def __init__(self):
        self._panels: Dict[str, PanelEntry] = {}

    def register(self, pid: str, panel: Renderable, icon: str = "", color: tuple = None, visible: bool = False):
        self._panels[pid] = PanelEntry(pid, panel, visible, icon, color or (1,1,1,1))

    def toggle(self, pid: str):
        if pid in self._panels:
            self._panels[pid].visible = not self._panels[pid].visible

    def set_visible(self, pid: str, is_visible: bool):
        if pid in self._panels:
            self._panels[pid].visible = is_visible

    def is_visible(self, pid: str) -> bool:
        return self._panels[pid].visible if pid in self._panels else False

    def render_all(self, state: Any, **context):
        """
        Iterates registered panels. If visible, calls their render method.
        Handles the close signal (return value False).
        """
        for entry in self._panels.values():
            if not entry.visible:
                continue
            
            # The panel render method should return False if the user closed it via 'X'
            keep_open = entry.instance.render(state, **context)
            if keep_open is False:
                entry.visible = False

    def get_entries(self) -> List[PanelEntry]:
        return list(self._panels.values())