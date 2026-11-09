from collections import deque
from queue import Empty, Full
from types import SimpleNamespace

from src.server import server_process


class QueueLike:
    def __init__(self, items=()):
        self.items = deque(items)
        self.values = []

    def get_nowait(self):
        if not self.items:
            raise Empty
        return self.items.popleft()

    def put(self, value):
        self.values.append(value)

    def put_nowait(self, value):
        self.values.append(value)


class FakeSession:
    def __init__(self, action_queue=None, ack_queue=None):
        self.state = object()
        self.action_queue = action_queue
        self.ack_queue = ack_queue
        self.commands = []
        self.saves = 0
        self.deltas = []

    def receive_command(self, envelope):
        self.commands.append(envelope.value)

    def save_map_changes(self):
        self.saves += 1

    def tick(self, delta):
        self.deltas.append(delta)
        if len(self.deltas) == 1:
            self.action_queue.items.append("SAVE_MAP_CHANGES")
            self.action_queue.items.append(Envelope("catch-up"))
            self.ack_queue.items.append(2)


class Envelope:
    def __init__(self, value):
        self.value = value


class Clock:
    step_seconds = 0.1

    def __init__(self):
        self.consumes = 0

    def consume(self, elapsed):
        self.consumes += 1
        return [0.1, 0.1] if self.consumes == 1 else []


class Snapshots:
    def __init__(self):
        self.acknowledged = []
        self.encoded = []

    def acknowledge(self, sequence):
        self.acknowledged.append(sequence)

    def encode(self, state):
        self.encoded.append(state)
        return f"packet-{len(self.encoded)}"


class Event:
    def __init__(self, states):
        self.states = deque(states)

    def is_set(self):
        return self.states.popleft() if self.states else True


def install_runtime(monkeypatch, *, session=None, create_error=None, event_states=(False, False, True)):
    clock = Clock()
    snapshots = Snapshots()
    create_calls = []
    progress = QueueLike()
    config_paths = []
    monkeypatch.setattr(server_process, "GameConfig", lambda path: config_paths.append(path) or "config")

    def create_headless(config, *, progress_cb, save_name, player_tag):
        create_calls.append((config, save_name, player_tag))
        progress_cb(0.5, "Loading")
        if create_error is not None:
            raise create_error
        return session

    monkeypatch.setattr(server_process, "GameSession", SimpleNamespace(create_headless=create_headless))
    monkeypatch.setattr(server_process, "FixedStepClock", lambda **kwargs: clock)
    monkeypatch.setattr(server_process, "StateSnapshotEncoder", lambda: snapshots)
    return clock, snapshots, create_calls, progress, config_paths, Event(event_states)


def test_drain_queue_collects_values_until_empty():
    queue = QueueLike([1, 2, 3])

    assert server_process._drain_queue(queue) == [1, 2, 3]
    assert server_process._drain_queue(queue) == []


def test_server_process_routes_controls_between_fixed_steps_and_handles_full_state_queue(monkeypatch, capsys):
    actions = QueueLike(["SAVE_MAP_CHANGES", Envelope("outer"), object()])
    acknowledgements = QueueLike([1])
    session = FakeSession(actions, acknowledgements)
    clock, snapshots, create_calls, progress, paths, shutdown = install_runtime(
        monkeypatch,
        session=session,
    )
    state_queue = QueueLike()
    state_queue.put_nowait = lambda value: (
        state_queue.values.append(value) if not state_queue.values else (_ for _ in ()).throw(Full)
    )
    times = iter([10.0, 10.01, 10.02, 10.03, 10.04])
    sleeps = []
    monkeypatch.setattr(
        server_process,
        "CommandEnvelope",
        Envelope,
    )
    monkeypatch.setattr(
        server_process,
        "time",
        SimpleNamespace(perf_counter=lambda: next(times), sleep=sleeps.append),
    )

    server_process.run_server_process(
        "config-root",
        actions,
        state_queue,
        progress,
        save_name="save-1",
        shutdown_event=shutdown,
        player_tag="USA",
        snapshot_ack_queue=acknowledgements,
    )

    assert paths[0].name == "config-root"
    assert create_calls == [("config", "save-1", "USA")]
    assert progress.values == [
        ("PROGRESS", 0.5, "Loading"),
        ("READY", 1.0, "Engine Started"),
    ]
    assert session.saves == 2
    assert session.commands == ["outer", "catch-up"]
    assert session.deltas == [0.1, 0.1]
    assert snapshots.acknowledged == [1, 2]
    assert len(snapshots.encoded) == 2
    assert state_queue.values == ["packet-1"]
    assert len(sleeps) == 2
    assert "Ignoring unsupported action payload object" in capsys.readouterr().out


def test_server_process_reports_session_creation_failure(monkeypatch):
    clock, snapshots, create_calls, progress, paths, shutdown = install_runtime(
        monkeypatch,
        create_error=RuntimeError("bad save"),
    )
    state_queue = QueueLike()
    actions = QueueLike()

    server_process.run_server_process(
        "missing-root",
        actions,
        state_queue,
        progress,
        shutdown_event=shutdown,
    )

    assert len(create_calls) == 1
    assert progress.values == [("PROGRESS", 0.5, "Loading"), ("ERROR", 0.0, "bad save")]
    assert state_queue.values == []
    assert snapshots.encoded == []


def test_server_process_exits_on_pre_set_shutdown_event(monkeypatch):
    session = FakeSession(QueueLike(), QueueLike())
    clock, snapshots, create_calls, progress, paths, shutdown = install_runtime(
        monkeypatch,
        session=session,
        event_states=(True,),
    )
    times = iter([0.0])
    monkeypatch.setattr(
        server_process,
        "time",
        SimpleNamespace(perf_counter=lambda: next(times), sleep=lambda value: None),
    )
    state_queue = QueueLike()

    server_process.run_server_process(
        "config-root",
        QueueLike(),
        state_queue,
        progress,
        shutdown_event=shutdown,
    )

    assert session.deltas == []
    assert state_queue.values == []
    assert snapshots.encoded == []
    assert progress.values[-1] == ("READY", 1.0, "Engine Started")


def test_server_process_exits_on_shutdown_command_before_ticking(monkeypatch):
    actions = QueueLike(["SHUTDOWN"])
    session = FakeSession(actions, QueueLike())
    clock, snapshots, create_calls, progress, paths, shutdown = install_runtime(
        monkeypatch,
        session=session,
        event_states=(False,),
    )
    monkeypatch.setattr(
        server_process,
        "time",
        SimpleNamespace(perf_counter=lambda: 0.0, sleep=lambda value: None),
    )

    server_process.run_server_process(
        "config-root",
        actions,
        QueueLike(),
        progress,
        shutdown_event=shutdown,
    )

    assert session.deltas == []
    assert snapshots.encoded == []


def test_server_process_checks_shutdown_between_catch_up_steps(monkeypatch):
    actions = QueueLike()

    class ShutdownAfterFirstTick(FakeSession):
        def tick(self, delta):
            self.deltas.append(delta)
            actions.items.append("SHUTDOWN")

    session = ShutdownAfterFirstTick(actions, QueueLike())
    clock, snapshots, create_calls, progress, paths, shutdown = install_runtime(
        monkeypatch,
        session=session,
        event_states=(False,),
    )
    monkeypatch.setattr(
        server_process,
        "time",
        SimpleNamespace(perf_counter=lambda: 0.0, sleep=lambda value: None),
    )
    state_queue = QueueLike()

    server_process.run_server_process(
        "config-root",
        actions,
        state_queue,
        progress,
        shutdown_event=shutdown,
    )

    assert session.deltas == [0.1]
    assert len(snapshots.encoded) == 1
    assert state_queue.values == ["packet-1"]
