# Research & Technical Rationale: Multi-Process IPC Architecture

## Decisions & Alternatives

### 1. Inter-Process Communication Channel Strategy
- **Decision**: Python `multiprocessing.Queue` divided into four dedicated channels:
  - `action_queue`: Client -> Server (commands, actions, raw string directives).
  - `state_queue`: Server -> Client (serialized Arrow IPC binary bytes of `GameState`).
  - `progress_queue`: Server -> Client (boot status tuples `(type, progress_float, status_text)`).
  - `snapshot_ack_queue`: Client -> Server (last successfully decoded sequence used as the delta base).
- **Rationale**: Isolates high-volume UI user inputs, acknowledgement traffic, heavy binary state transfers, and startup diagnostics. Prevents state snapshot queue backpressure from blocking user input submissions.
- **Alternatives Considered**: 
  - *Single Shared Queue*: Caused input contention and state serialization blockage during initial asset compilation.
  - *Shared Memory Shared Array (multiprocessing.shared_memory)*: Higher memory management complexity requiring rigid fixed-size buffers, inappropriate for dynamic Polars DataFrames.

### 2. State Binary Serialization Format
- **Decision**: Serialize each Polars table as an Apache Arrow IPC byte buffer inside a protocol-versioned Python queue packet.
- **Rationale**: Arrow preserves typed columnar values and lets deltas carry only changed tables. The multiprocessing queue still transports Python packet objects and byte buffers; this is not zero-copy shared memory.
- **Alternatives Considered**: 
  - *Standard `pickle`*: Exceedingly slow for 100,000+ row region/country tables (15-40ms per tick), causing micro-stutters.
  - *JSON Serialization*: High CPU parse overhead and precision loss on floating-point economic indicators.

### 3. Server Process Pacing & Loop Timing
- **Decision**: Fixed 10 TPS (100ms interval) using `time.perf_counter()` and dynamic `time.sleep()`.
- **Rationale**: Provides sufficient simulation resolution for geopolitical macroeconomic trends, demographic steps, and unit movements while keeping background CPU load under 5%.

## Open Runtime Throughput Follow-up

The original end-to-end launcher command test showed load-sensitive command completion under the expanded world systems. One run took 41.18 seconds and missed its 30-second command-result window (`tick=6`, no result in the latest client snapshot); an immediate isolated rerun passed in 41.90 seconds with the command applied at tick 7. These wall times include world startup and do not isolate command latency, so they are evidence of a throughput/latency risk rather than a stable benchmark.

The later [`SIMULATION_OPTIMIZATION_REPORT.md`](../../docs/SIMULATION_OPTIMIZATION_REPORT.md) records targeted AI, route-preparation, and history-sampling optimizations on a three-tick workload, with state/table hashes preserved. That work supersedes the original pass's statement that no optimization had been attempted, but it does not isolate end-to-end command latency or establish the visible-client framerate gate. Those remain separate acceptance questions.
