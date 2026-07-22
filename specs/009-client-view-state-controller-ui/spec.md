# Feature Specification: Client View State Architecture, Navigation & Audio Services

## User Scenarios & Testing

### Primary User Story
As a player navigating OpenPower, I want a unified view management system (`NavigationService`), background audio playback (`AudioService`), and structured HUD component bars (`CentralBar`, `SystemBar`, `ToggleBar`, `ContextMenu`), so that navigating screens, booting games, toggling panels, and playing music occurs smoothly across all views.

### Acceptance Scenarios
1. **Navigation Service View Stack**: **Given** user interactions, **When** `NavigationService` switches views (`show_main_menu`, `show_loading`, `show_new_game_screen`, `show_load_game_screen`, `show_game_view`, `show_editor_loading`), **Then** current view resources are released and the target `View` instance is displayed.
2. **Audio Track Management (`AudioService`)**: **Given** background music tracks (e.g. `World_of_Leaders.mp3`), **When** `play_music` is invoked with a track path, **Then** previous streams stop cleanly, volume is applied (\(0.0 \le \text{vol} \le 1.0\)), and looping audio streams without restarting if the same track is already active.
3. **Async Task Loading Views (`LoadingView` & `EditorLoadingTask`)**: **Given** session startup or map editor initialization, **When** `LoadingView` runs an asynchronous loading task, **Then** progress callback updates render visual loading bars until task completion.
4. **Window Boot & Proxy Handshake (`MainWindow`)**: **Given** application launch (`main.py`), **When** `MainWindow.setup` schedules `start_client_proxy`, **Then** `ClientSessionProxy` spawns the background process and `check_server_boot` polls `progress_queue` at 60Hz.

### Edge Cases
- Missing audio files: `AudioService` logs a non-fatal error and continues without crashing the game loop.
- Rapid view switching during active loading tasks: `NavigationService` ensures previous view event listeners and schedules are cleaned up before view transition.
- Window resizing (`on_resize`): Viewport and scissor rects are updated (`ctx.viewport = (0, 0, width, height)`), forwarding resize events to `current_view`.

## Component & Service Architecture Table

| Service / Component File | Primary Responsibility | Key Classes / Functions |
| :--- | :--- | :--- |
| `src/client/services/navigation_service.py` | View transition stack manager | `show_main_menu`, `show_game_view`, `show_editor_loading` |
| `src/client/services/audio_service.py` | Music & SFX stream manager | `play_music`, `stop_music`, `set_volume`, `is_playing` |
| `src/client/services/imgui_service.py` | Dear ImGui integration & font loader | `ImGuiService`, `font_loader.py` |
| `src/client/services/network_client_service.py` | Client IPC wrapper | `NetworkClient` |
| `src/client/tasks/editor_loading_task.py` | Async editor initialization task | `EditorLoadingTask`, `EditorContext` |
| `src/client/tasks/new_game_task.py` | New campaign initialization task | `NewGameTask` |
| `src/client/ui/components/hud/central_bar.py` | Top HUD date/speed display | `CentralBar` |
| `src/client/ui/components/hud/system_bar.py` | Menu & view action bar | `SystemBar` |
| `src/client/ui/components/hud/toggle_bar.py` | Map mode & inspector toggle bar | `ToggleBar` |
| `src/client/ui/components/hud/context_menu.py` | Mouse right-click context menu | `ContextMenu` |
| `utils/validate_economy.py` | Offline TOML data validation tool | `validate_file`, `load_gdp_data` |

## Success Criteria

- **SC-001**: Smooth View Transitions: View switches complete within 1 frame (16ms) without memory leaks or dangling event handlers.
- **SC-002**: Audio Stream Continuity: Music plays continuously across view transitions without audio pops or stutters.
- **SC-003**: Reliable Asynchronous Boot: 100% of progress messages from `progress_queue` render accurately on `ServerBootView`.

## Assumptions & Dependencies

- **Assumption**: Arcade audio subsystem (`arcade.load_sound`, `arcade.play_sound`) manages sound streams.
- **Dependency**: ImGui bundle primitives render HUD overlay bars.
