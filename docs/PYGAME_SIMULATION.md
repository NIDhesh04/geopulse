# GeoPulse: Pygame Visual Simulation System
## Interactive 2D Simulation of Sequential Two-Edge Decision & Dynamic Rerouting

**Document:** `docs/PYGAME_SIMULATION.md`  
**System:** GeoPulse Major Project  
**Author:** GeoPulse Architecture & Core Engineering  
**Version:** 1.0  
**Status:** Approved & Implemented  

---

## 1. Overview & Demonstration Objective

The **GeoPulse Pygame Visual Simulation** is an interactive, real-time graphical application engineered to visually demonstrate the core sequential two-edge routing and dynamic rerouting algorithms.

Unlike decoupled visual mockups, the Pygame frontend is **directly connected to the genuine GeoPulse routing engine**:
- Uses the same `CandidateGenerator` to identify eligible outgoing edges.
- Uses the same `TwoEdgeSelector` and polymorphic `BaseDecisionStrategy` implementations (Greedy, Destination-Aware, Limited Lookahead, Adaptive).
- Uses the same physical kinematic travel-time edge costs $w_e = L_e / (v_e / 3.6)$ with crawl-speed floors ($v_e \ge 3.0\text{ km/h}$).
- Uses the same road network topologies:
  1. A structured **Custom Urban Grid Network** for clean presentation clarity.
  2. The full **Bhubaneswar OpenStreetMap Network** with 18,260 nodes and 46,679 directed edges.

---

## 2. Visual Architecture & Modular Layout

The display canvas ($1280 \times 720\text{ px}$) is partitioned into two distinct functional zones:

```
┌────────────────────────────────────────────────────────┬──────────────────────┐
│                                                        │   GEOPULSE HUD UI    │
│                                                        │   (Width: 340 px)    │
│                                                        ├──────────────────────┤
│                                                        │  JOURNEY TELEMETRY   │
│                 ROAD NETWORK CANVAS                    │  • Origin & Dest     │
│                   (Width: 940 px)                      │  • Current Node      │
│                                                        │  • Elapsed Time & m  │
│   • Background Grid (Dark Slate #0f172a)               │  • Decisions / Hops  │
│   • Road Congestion Overlay:                           │  • Dynamic Reroutes  │
│       - Green (Free-flow >= 35 km/h)                   ├──────────────────────┤
│       - Amber (Moderate 20-35 km/h)                    │ TWO-EDGE COMPARISON  │
│       - Red (Congested < 20 km/h)                      │ ┌────────┐┌────────┐ │
│   • Candidate Edge A Highlight (Cyan #06b6d4)          │ │ Cand A ││ Cand B │ │
│   • Candidate Edge B Highlight (Orange #f97316)        │ │ Speed  ││ Speed  │ │
│   • Selected Edge Highlight (Emerald #10b981)          │ │ Cost   ││ Cost   │ │
│   • Traversed Path History (Indigo #6366f1)            │ │ Score  ││ Score  │ │
│   • Origin (Green) & Destination (Gold) Markers        │ └────────┘└────────┘ │
│   • Smooth Animated Vehicle with Directional Heading   │ ┌──────────────────┐ │
│                                                        │ │ Decision Reason  │ │
│                                                        │ └──────────────────┘ │
│                                                        ├──────────────────────┤
│                                                        │ SIMULATION CONTROLS  │
│                                                        │ [Resume] [Step] [Rst]│
│                                                        │ [1x]     [2x]   [5x] │
│                                                        │ [Mode: Strategy...]  │
│                                                        │ [Network: Grid/OSM]  │
└────────────────────────────────────────────────────────┴──────────────────────┘
```

---

## 3. Intersection Decision Progression (Step-by-Step)

At every intersection along the vehicle's journey:

1. **Approach & Decision Pause:**
   The vehicle enters the intersection node and pauses (or slows down) for an inspection duration (default $1.0\text{ s}$, customizable).
2. **Candidate Generation & Highlighting:**
   - The two eligible outgoing branches are selected and visually highlighted:
     - **Candidate Edge A:** Glowing Cyan line (`#06b6d4`) with endpoint circle.
     - **Candidate Edge B:** Glowing Orange line (`#f97316`) with endpoint circle.
3. **HUD Comparison Display:**
   The side panel populates two side-by-side cards with real-time telemetry:
   - Metric length ($L_e$)
   - Predicted traversal speed ($v_e$)
   - Traversal travel time ($w_e$)
   - Decision score ($\text{Score}(e)$)
4. **Winner Selection:**
   The decision directive banner displays the winning branch and rationale. The chosen candidate box glows green.
5. **Kinematic Motion:**
   The selected edge flashes Neon Green (`#10b981`). The vehicle sprite rotates to match the edge azimuth and animates smoothly to the next node.
6. **Dynamic Traffic Alert:**
   When traffic congestion updates mid-journey, affected edges turn Crimson Red (`#ef4444`), an alert banner flashes in the HUD, and continuation costs are recalculated.

---

## 4. Interactive Keyboard & Mouse Controls

| Input Control | Action | Description |
|---|---|---|
| **SPACE** | Pause / Resume | Toggles continuous playback. |
| **N** | Step Forward | Manually advances the vehicle by one decision / edge traversal. |
| **R** | Reset | Resets vehicle to origin and clears journey history. |
| **1 / 2 / 5** | Speed Multiplier | Sets animation speed to $1\times$, $2\times$, or $5\times$. |
| **S / Mode Click** | Cycle Strategy | Cycles between Greedy, Destination-Aware, Lookahead-2, Lookahead-3, and Adaptive. |
| **ESC / Q** | Quit | Closes the Pygame simulation window. |

---

## 5. Execution Commands

### 5.1 Interactive Demonstration (Custom Grid Network)
```bash
.venv\Scripts\python.exe -m src.pygame_simulation.main --network custom --strategy destination_aware
```

### 5.2 Interactive Demonstration (OSM Bhubaneswar Real Network)
```bash
.venv\Scripts\python.exe -m src.pygame_simulation.main --network osm --strategy lookahead_2
```

### 5.3 Headless Automated Validation (for CI / Academic Evaluation)
```bash
.venv\Scripts\python.exe -m src.pygame_simulation.main --headless --duration 3.0
```
