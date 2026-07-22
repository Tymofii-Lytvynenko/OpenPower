# Research & Technical Rationale: Multi-Process IPC Architecture

## Decisions & Alternatives

### 1. Inter-Process Communication Channel Strategy
- **Decision**: Python `multiprocessing.Queue` divided into 3 dedicated channels:
  - `action_queue`: Client -> Server (commands, actions, raw string directives).
  - `state_queue`: Server -> Client (serialized Arrow IPC binary bytes of `GameState`).
  - `progress_queue`: Server -> Client (boot status tuples `(type, progress_float, status_text)`).
- **Rationale**: Isolates high-volume UI user inputs from heavy binary state transfers and startup diagnostics. Prevents state snapshot queue backpressure from blocking user input submissions.
- **Alternatives Considered**: 
  - *Single Shared Queue*: Caused input contention and state serialization blockage during initial asset compilation.
  - *Shared Memory Shared Array (multiprocessing.shared_memory)*: Higher memory management complexity requiring rigid fixed-size buffers, inappropriate for dynamic Polars DataFrames.

### 2. State Binary Serialization Format
- **Decision**: Zero-Copy Apache Arrow IPC Streams (`df.write_ipc()` / `pl.read_ipc()`).
- **Rationale**: Apache Arrow IPC serializes columnar Polars DataFrames into contiguous memory buffers in < 2ms, enabling 30Hz state updates without Python object pickling overhead.
- **Alternatives Considered**: 
  - *Standard `pickle`*: Exceedingly slow for 100,000+ row region/country tables (15-40ms per tick), causing micro-stutters.
  - *JSON Serialization*: High CPU parse overhead and precision loss on floating-point economic indicators.

### 3. Server Process Pacing & Loop Timing
- **Decision**: Fixed 10 TPS (100ms interval) using `time.perf_counter()` and dynamic `time.sleep()`.
- **Rationale**: Provides sufficient simulation resolution for geopolitical macroeconomic trends, demographic steps, and unit movements while keeping background CPU load under 5%.
