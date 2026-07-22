from __future__ import annotations

import multiprocessing as mp
from dataclasses import dataclass

from src.core.map_data import RegionMapData


@dataclass(frozen=True)
class ServerProcessBundle:
    map_data: RegionMapData
    action_queue: mp.Queue
    state_queue: mp.Queue
    progress_queue: mp.Queue
    snapshot_ack_queue: mp.Queue
    process: mp.Process
