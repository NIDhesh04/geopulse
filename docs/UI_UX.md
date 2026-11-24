# UI/UX and map visualization — approved Topic 8

**Fact:** Consolidated on 2026-11-23 from Topic 8 approvals. These are design specifications, not implemented screens. React/TypeScript and server-authoritative state follow ARCHITECTURE.md.

## Police control room

- **Decision:** Use a desktop map-centered layout: top run/scenario/clock/connection/playback bar; left fleet, search, zone-filter and mission panel; central map; right entity inspector; and collapsible bottom Alerts/Events panel.
- **Decision:** Selecting an ambulance synchronizes its fleet row, map marker, route, and inspector. Selection does not automatically recenter repeatedly; Locate and Follow are explicit actions.
- **Decision:** Junction inspection shows phase/timer, movement queues, pending requests, active grant, and recovery state. Signal colors are read-only. No unrestricted force-green control exists.
- **Decision:** Incident inspection shows affected roads, report status/timing, and review actions. Physical-effect details appear only in Simulation Truth; operational inspection must not leak hidden effects.
- **Decision:** Mission activation collects ambulance, departure entry, destination hospital, and priority authorization. Display Pending after acceptance until backend APPLIED/REJECTED is received. Rejection shows the reason; do not optimistically display a mission as active.
- **Decision:** Suspend priority, Retry route, Confirm report, and Acknowledge alert remain distinct actions. Acknowledgement does not remove unresolved alerts or change road availability.
- **Decision:** Playback provides Play/Pause, Step 1 second while paused, and 1x/5x/10x/30x/60x. Restart requires confirmation and creates a new run rather than overwriting history.
- **Decision:** Bottom panel defaults to unresolved Alerts with neighboring Events tab. Events follow server sequence. New items neither steal focus nor scroll a user away from older inspected content; expose a new-items indicator instead.

## Route explanation inspector

- **Decision:** Display candidate movements with estimated road seconds, junction waiting seconds, remaining path cost, and outcome (selected, alternative, blocked, unknown). Highlight the winner.
- **Decision:** Show decision simulation timestamp and routing revision. Expand rows for live/historical sources, fallback reasons, and forecast-horizon failures.
- **Decision:** Excluded alternatives receive plain-English reasons, never an unexplained infinity symbol. Distinguish unknown estimate from known physical blockage.
- **Decision:** A routing explanation represents its decision snapshot and must not be presented as current physical truth when newer state exists.

## Driver view

- **Decision:** Provide a narrow-screen-friendly next-maneuver banner, route map, destination, remaining distance, ETA, next-junction signal/priority state, connection indicator, stop/reroute messages, and obstruction-report action.
- **Decision:** Follow the selected ambulance by default. User dragging disables follow and exposes Recenter. Selection and camera behavior are separate from the police map.
- **Decision:** Distinguish priority requested, granted, downstream blocked, and suspended. Green does not promise available receiving storage. Ordinary red waiting is not a road-blockage alert.
- **Decision:** Prefill obstruction reports with the current road. Accepted submission says Awaiting operator review; it does not label the road confirmed closed.

## ETA and state freshness

- **Decision:** Use the latest server-provided route estimate and its calculation time. Derive arrival clock time from that snapshot; countdowns use simulation time, never elapsed browser wall time.
- **Decision:** If estimated arrival has elapsed without actual arrival, show Estimate exceeded instead of perpetual zero. If no feasible route estimate exists, show ETA unavailable and its reason. On arrival show measured journey time.
- **Decision:** On disconnect/stale updates, freeze the last confirmed display and visibly identify stale status. Never continue indefinitely, infer unconfirmed junction crossings, or conceal uncertainty with client-generated reroutes.
- **Decision:** Driver position animation interpolates confirmed server positions only. Simulation pause also pauses simulation-time displays.

## Map rendering and information modes

- **Decision:** Use MapLibre GL JS. The default synthetic network uses locally styled map background/assets without mandatory external map tiles. Optional geographic context uses junction coordinates with a visible synthetic-network label.
- **Decision:** Geographic placement does not change simulated road lengths or imply that a grid is the actual road network of the displayed city. No Google Maps services or paid data are introduced.
- **Decision:** Information modes are mutually exclusive: Operational, Ambulance Routing, and Simulation Truth. Geographic context is an independent background toggle.
- **Decision:** Operational displays confirmed reports and explicitly available observations with timestamps, using historical estimates where unavailable. It is not an unrestricted ground-truth view.
- **Decision:** Ambulance Routing displays the selected ambulance's routing snapshot, live neighborhood, predictions, and route. It requires an ambulance selection; source visibility follows that ambulance's approved information boundary.
- **Decision:** Simulation Truth explicitly exposes physical incidents/actual occupancy for demonstration. Switching views never changes what a routing strategy can access.
- **Decision:** Mode-appropriate toggles cover roads, signals, ambulances, incidents, queue indicators, and zones. Keep a matching legend visible.
- **Decision:** In routing mode, solid edges indicate live-source estimates and dashed edges historical-source estimates. A separate cyan route highlight preserves visible source styling. Mark fallback edges and explain on selection. De-emphasize rather than hide alternatives.
- **Decision:** Label routing snapshot time. Congestion uses sequential neutral/purple intensity; signal and exception colors remain semantically distinct.
- **Decision:** Ordinary traffic appears as road styling, queue indicators, and counts. Ambulances have individual markers. Any future decorative civilian particles must not imply individual civilian simulation.
- **Assumption (implementation follow-up):** Finalize the local-coordinate to render-coordinate adapter and optional basemap source/attribution before implementing map packaging. Synthetic mode must remain usable without network tile access.

## Responsive layout and accessibility

| Width | Approved behavior |
|---|---|
| **Decision:** >=1280 px | Full fleet/map/inspector desktop layout |
| **Decision:** 900–1279 px | Collapsible fleet; inspector overlays map |
| **Decision:** <900 px | Compact control room with drawers, only one open at a time |
| **Decision:** Driver view at all widths | Navigation-first layout using additional width for map space |

- **Decision:** On narrow screens, avoid covering the selected vehicle/next maneuver with controls. Touch targets are at least 44 px.
- **Decision:** Keyboard users can select entities and inspect the same information as map users. Escape closes drawers; closing restores focus to the trigger. Status cannot depend exclusively on color or hover.
- **Decision:** Reduced-motion mode removes decorative movement and camera flights. Important information never flashes. Selection/panel transitions normally take about 150–200 ms.

## Visual tokens

| Token | Approved initial value |
|---|---|
| **Decision:** App background | #0B1118 |
| **Decision:** Panel | #131C26 |
| **Decision:** Raised surface | #1B2836 |
| **Decision:** Border | #334455 |
| **Decision:** Primary text | #F1F5F9 |
| **Decision:** Secondary text | #A8B8C8 |
| **Decision:** Route/selection | #22D3EE |
| **Decision:** Signal green | #4ADE80 |
| **Decision:** Warning/amber | #FBBF24 |
| **Decision:** Stop/error | #FB7185 |
| **Decision:** Historical accent | #A78BFA |

- **Decision:** Bundle Inter locally, use tabular timer numerals, a 4 px spacing scale, and restrained 8–12 px radii. Body text starts at 16 px, operational labels 14 px, and secondary metadata 12 px.
- **Decision:** Centralize tokens rather than scattering color/spacing literals. Validate contrast in actual rendered combinations; token approval alone is not contrast certification.

## Landing and scenario selection

- **Decision:** Keep a concise landing page with purpose, a real simulation preview, and entry points to control-room and driver views.
- **Decision:** Scenario cards show description, network size, ambulance count, incident summary, and Synthetic scenario label. Generated imagery is limited to the hero and scenario-selection surfaces.
- **Decision:** Generated art does not replace the live preview or imply footage of operational deployment. Operational polish comes from clarity, map behavior, selection, and confirmed animation.

## Verification and remaining work

- **Decision:** Verify synchronized selection without unwanted camera movement, command Pending/APPLIED/REJECTED behavior, non-scroll-stealing event arrival, and acknowledged-but-unresolved alerts.
- **Decision:** Verify mode-specific information projections do not leak hidden incidents into operational/driver views or routing inputs. Verify snapshot time/source legends and unknown-cost explanations.
- **Decision:** Verify simulation-time ETA at all playback speeds, overdue/unavailable/disconnected states, and driver follow/recenter/report behavior.
- **Decision:** Verify all three responsive ranges, keyboard/focus behavior, touch targets, reduced motion, contrast, and synthetic map operation without external tiles.
- **Assumption (remaining implementation detail):** Exact operational observation retention/projection, stale-connection threshold, rendering adapter, and concrete basemap/art assets must be specified before their UI milestone. These do not authorize expanding the router's information access.
