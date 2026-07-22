# Feature Specification: Treaties, Alliances & Map Overlay System

## User Scenarios & Testing

### Primary User Story
As a player surveying global geopolitics, I want diplomatic treaties, military alliances, defensive pacts, and active conflicts visually highlighted via dynamic political map modes and overlays, so that I can immediately assess international power blocs and diplomatic relationships.

### Acceptance Scenarios
1. **Diplomatic Treaty Registry**: **Given** active treaties loaded from data tables (`countries_treaties.toml`, `countries_wars.toml`), **When** the territory system updates, **Then** authorization relationships (allies, non-aggression, defensive pacts, active wars) are maintained in state memory.
2. **Empire Mode Dynamic Map Coloring**: **Given** a player selecting a target nation on the global map, **When** Empire Mode map mode is activated, **Then** the selected nation renders in green, allies in blue, active enemies in vibrant red, and neutral states in charcoal.
3. **Smooth Map Shader Transitions**: **Given** a player toggling between political, economic, and diplomatic map views, **When** switching modes, **Then** region colors transition smoothly via fragment shader uniforms without visual flickering.

### Edge Cases
- Nations belonging to multiple overlapping multilateral defensive alliances.
- Declarations of war breaking active non-aggression treaties mid-campaign.
- Civil wars or nation fracturing resulting in new country IDs inheriting alliance treaties.

## Functional Requirements

- **FR-001**: Treaty Authorization Registry: The system MUST parse and maintain treaty relationships, defensive pacts, alliance blocs, and active war statuses.
- **FR-002**: Empire Mode Color Map Generator: The map renderer MUST dynamically compute region color palettes based on the selected player/country perspective and active diplomatic statuses.
- **FR-003**: GPU Map Shader Rendering: Region fill colors, border highlights, and diplomatic overlays MUST be rendered in GPU fragment shaders.
- **FR-004**: Interactive Region Selection: Clicking any geographic region MUST query regional ownership, active treaties, and update map focus.

## Key Entities & Data Model

- **TreatyRecord**: Represents treaty ID, signatory country IDs, treaty type (alliance, defensive pact, trade deal, non-aggression), creation date, and expiration date.
- **WarRecord**: Tracks war ID, aggressor alliance IDs, defender alliance IDs, start date, and accumulated war score.

## Success Criteria

- **SC-001**: Visual Clarity: Map overlays immediately convey alliance network topology with 100% color distinction across diplomatic states.
- **SC-002**: Real-Time Shader Updates: Changing selected country focus recalculates global map region colors in under 2ms.
- **SC-003**: Data Consistency: 100% of treaty relationship entries in TOML datasets are correctly parsed into simulation state tables.

## Assumptions & Dependencies

- **Assumption**: `countries_treaties.toml` and `countries_wars.toml` datasets are loaded by `territory_system.py`.
- **Dependency**: Arcade map fragment shaders in `src/client/renderers/map_renderer.py` render region colors.
