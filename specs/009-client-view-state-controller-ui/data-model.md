# Data Model: Client View State Architecture, Navigation & Audio Services

This feature adds runtime client state only. It does not add authoritative game tables or persisted save fields.

## View Transition

| Field | Type | Owner | Rule |
|---|---|---|---|
| current view | `arcade.View | None` | Arcade window | Exactly one view receives active window events. |
| target view | `arcade.View` | `NavigationService` during transition | Constructed with its required session/config/context, then handed to `Window.show_view`. |
| lifecycle | Arcade hide/show callbacks | Arcade window | Old view cleanup completes through framework lifecycle; services attached to the window outlive views. |

## Loading Task

| Field | Type | Rule |
|---|---|---|
| progress | float | Clamp to `[0.0, 1.0]` for presentation. |
| status text | string | Describes the current user-visible stage. |
| state | pending/running/succeeded/failed/cancelled | One terminal state; a hidden loading view cannot later navigate to a result view. |
| result | task-specific object | Delivered to the next view only on the UI thread after success. |
| error | exception or safe display text | Failure is delivered once; it must not be silently discarded. |
| cancellation | cooperative signal | Checked at safe task boundaries; it must not call UI/OpenGL APIs from the worker. |

## Audio Service

| Field | Type | Rule |
|---|---|---|
| current track identity | normalized path or `None` | Equal path identities do not restart an actively playing stream. |
| sound/player | Arcade audio handle or `None` | Retained for the active stream lifetime. |
| stream | Arcade playback handle or `None` | At most one service-managed music stream is active. |
| volume | float | Always bounded to `[0.0, 1.0]`; a live stream receives updates. |
| looping | bool | Passed to the audio backend when a new stream starts. |

## Window Boot State

| Field | Type | Rule |
|---|---|---|
| progress | float | Bounded to `[0.0, 1.0]` and updated from server progress messages. |
| status | string | Latest boot step shown by `ServerBootView`. |
| error | string or `None` | Terminal boot failure is visible and stops scheduled polling. |
| session proxy | `ClientSessionProxy | None` | Owns communication/process lifecycle; all state reads and actions cross the session boundary. |

## HUD Action

| Field | Type | Rule |
|---|---|---|
| id/label/shortcut | string | Stable action identity and accessible description. |
| callback | callable | Sends a client navigation/UI callback or semantic `GameAction`; does not mutate authoritative state. |
| visible/enabled/badge | presentation state | Derived from the current view model or panel registry. |

## Existing Interfaces

`LoadingTask` in `src/client/interfaces/loading.py` describes task progress/status/result; `SessionPort` in `src/shared/protocols.py` describes the client/server-facing operations. No new persistent schema or public service API is introduced.

## Session Factory

| Field | Type | Rule |
|---|---|---|
| configuration | `GameConfig` | Supplied by the application entry point. |
| save name | string or `None` | `None` starts a new session; a name selects a persisted save. |
| player tag | string or `None` | Optional requested player identity for new-session setup. |
| result | client session protocol | Exposes the session port plus boot progress, ticking, map data, and shutdown; the concrete process bundle remains outside `src/client`. |
