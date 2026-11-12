import time
import os
from multiprocessing.queues import Queue
from multiprocessing.synchronize import Event
from queue import Empty, Full
from typing import Optional

from src.core.telemetry import PerformanceCollector
from src.server.telemetry_publisher import TelemetryPublisher
from src.shared.telemetry_types import TelemetryControl
from src.engine.clock import FixedStepClock
from src.server.session import GameSession
from src.shared.commands import CommandEnvelope
from src.shared.config import GameConfig
from src.shared.snapshots import StateSnapshotEncoder


def _drain_queue(queue_obj):
    items = []
    while True:
        try:
            items.append(queue_obj.get_nowait())
        except Empty:
            return items


def run_server_process(
    config_root,
    action_queue: Queue,
    state_queue: Queue,
    progress_queue: Queue,
    save_name: Optional[str] = None,
    shutdown_event: Optional[Event] = None,
    player_tag: Optional[str] = None,
    snapshot_ack_queue: Queue | None = None,
    telemetry_queue: Queue | None = None,
):
    from pathlib import Path

    config = GameConfig(Path(config_root))

    def progress_cb(progress: float, text: str) -> None:
        progress_queue.put(("PROGRESS", progress, text))

    try:
        session = GameSession.create_headless(
            config,
            progress_cb=progress_cb,
            save_name=save_name,
            player_tag=player_tag,
        )
        progress_queue.put(("READY", 1.0, "Engine Started"))
    except Exception as exc:
        progress_queue.put(("ERROR", 0.0, str(exc)))
        return

    telemetry = PerformanceCollector(os.getenv("OPENPOWER_TELEMETRY", "").lower() in {"1", "true", "yes", "on"})
    session.engine.telemetry = telemetry
    publisher = TelemetryPublisher(telemetry, telemetry_queue)
    # A client that stops receiving must not hold process shutdown in a queue feeder.
    for outbound in (state_queue, telemetry_queue):
        cancel_join = getattr(outbound, "cancel_join_thread", None)
        if callable(cancel_join):
            cancel_join()

    def control(message):
        if not isinstance(message, TelemetryControl):
            return False
        if message.operation == "reset":
            telemetry.reset()
        else:
            telemetry.set_enabled(message.operation == "enable")
        return True

    clock = FixedStepClock(step_seconds=0.1, max_catch_up_steps=5)
    snapshots = StateSnapshotEncoder()
    last_time = time.perf_counter()

    while True:
        if shutdown_event is not None and shutdown_event.is_set():
            return

        frame_start = time.perf_counter()
        elapsed = frame_start - last_time
        last_time = frame_start

        for incoming in _drain_queue(action_queue):
            if control(incoming):
                continue
            if incoming == "SHUTDOWN":
                return
            if incoming == "SAVE_MAP_CHANGES":
                session.save_map_changes()
                continue
            if isinstance(incoming, CommandEnvelope):
                session.receive_command(incoming)
                continue
            print(
                f"[ServerProcess] Ignoring unsupported action payload "
                f"{type(incoming).__name__}."
            )

        if snapshot_ack_queue is not None:
            for acknowledged_sequence in _drain_queue(snapshot_ack_queue):
                snapshots.acknowledge(int(acknowledged_sequence))

        steps = clock.consume(elapsed)
        if len(steps) > 1:
            telemetry.increment("simulation.scheduler.catchup_steps", len(steps) - 1)
        for fixed_delta in steps:
            # A catch-up batch can contain expensive world updates. Consume
            # controls between steps so pause and orders do not wait for all five.
            for incoming in _drain_queue(action_queue):
                if control(incoming):
                    continue
                if incoming == "SHUTDOWN":
                    return
                if isinstance(incoming, CommandEnvelope):
                    session.receive_command(incoming)
                elif incoming == "SAVE_MAP_CHANGES":
                    session.save_map_changes()
            if snapshot_ack_queue is not None:
                for acknowledged_sequence in _drain_queue(snapshot_ack_queue):
                    snapshots.acknowledge(int(acknowledged_sequence))
            session.tick(fixed_delta)
            if telemetry.enabled:
                with telemetry.measure("ipc.snapshot.encode_ms"):
                    packet = snapshots.encode(session.state)
                telemetry.increment("ipc.snapshots.produced")
                try:
                    size = sum(len(data) for data in packet["tables"].values())
                    size += sum(len(value["data"]) for value in packet["appended_tables"].values())
                    telemetry.gauge("ipc.snapshot.payload_bytes", size, "bytes")
                except Exception:
                    telemetry._log_failure()
            else:
                packet = snapshots.encode(session.state)
            try:
                state_queue.put_nowait(packet)
            except Full:
                telemetry.increment("ipc.snapshots.dropped")
                # Deltas remain cumulative from the last client acknowledgement.
                pass

        publisher.publish_if_due()
        sleep_time = max(
            0.0,
            clock.step_seconds - (time.perf_counter() - frame_start),
        )
        time.sleep(sleep_time)
