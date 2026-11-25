"""Pygame three-panel synchronized simulation renderer for GeoPulse.

Displays Static Dijkstra, Dynamic Dijkstra, and GeoPulse Two-Edge Selection
side by side on the exact same road network and traffic timeline, animates one
vehicle per panel using realized speeds, displays live per-panel telemetry, and
renders a final comparison summary once all three journeys complete.
"""

from __future__ import annotations

import os
import time
from typing import Dict, List, Optional, Set, Tuple

import pygame

from src.experiments.temporal_journey import Edge, STRATEGIES
from src.pygame_simulation.road_renderer import RoadRenderer
from src.pygame_simulation.temporal_comparison import StrategyAgentState, ThreeStrategySimulation
from src.pygame_simulation.vehicle_sprite import VehicleSprite


class ThreePanelComparisonRenderer:
    """Interactive Pygame window comparing Static, Dynamic, and GeoPulse routing."""

    BG_COLOR = (13, 19, 33)
    PANEL_BG = (19, 28, 46)
    CARD_BG = (28, 39, 61)
    BORDER = (56, 72, 102)
    TEXT_MAIN = (248, 250, 252)
    TEXT_MUTED = (148, 163, 184)
    ACCENT_CYAN = (6, 182, 212)
    ACCENT_ORANGE = (249, 115, 22)
    ACCENT_GREEN = (16, 185, 129)
    ACCENT_BLUE = (59, 130, 246)
    ACCENT_RED = (239, 68, 68)
    ACCENT_GOLD = (234, 179, 8)
    PLANNED_COLOR = (125, 211, 252)
    BTN_BG = (45, 59, 85)
    BTN_ACTIVE = (37, 99, 235)

    PANEL_ACCENTS = {
        "static_dijkstra": (59, 130, 246),
        "dynamic_dijkstra": (245, 158, 11),
        "geopulse_two_edge": (16, 185, 129),
    }

    VEHICLE_COLORS = {
        "static_dijkstra": ((59, 130, 246), (147, 197, 253, 85)),
        "dynamic_dijkstra": ((245, 158, 11), (252, 211, 77, 85)),
        "geopulse_two_edge": ((16, 185, 129), (110, 231, 183, 85)),
    }

    def __init__(
        self,
        simulation: ThreeStrategySimulation,
        headless: bool = False,
        window_size: Optional[Tuple[int, int]] = None,
    ):
        self.simulation = simulation
        self.headless = headless

        if self.headless:
            os.environ["SDL_VIDEODRIVER"] = "dummy"
        elif os.environ.get("SDL_VIDEODRIVER") == "dummy":
            os.environ.pop("SDL_VIDEODRIVER", None)

        pygame.init()
        pygame.font.init()

        if window_size is not None:
            self.width, self.height = int(window_size[0]), int(window_size[1])
        elif self.headless:
            self.width, self.height = 1360, 780
        else:
            info = pygame.display.Info()
            avail_w = info.current_w if info.current_w > 0 else 1360
            avail_h = info.current_h if info.current_h > 0 else 780
            self.width = max(1080, min(1440, avail_w - 60))
            self.height = max(660, min(840, avail_h - 80))

        pygame.display.set_caption(
            "GeoPulse — Static Dijkstra vs Dynamic Dijkstra vs GeoPulse Two-Edge Simulation"
        )
        flags = 0 if self.headless else pygame.RESIZABLE
        self.screen = pygame.display.set_mode((self.width, self.height), flags)
        self.clock = pygame.time.Clock()

        self.font_title = pygame.font.SysFont("Segoe UI, Arial", 19, bold=True)
        self.font_header = pygame.font.SysFont("Segoe UI, Arial", 15, bold=True)
        self.font_body = pygame.font.SysFont("Segoe UI, Arial", 13)
        self.font_small = pygame.font.SysFont("Segoe UI, Arial", 11)
        self.font_mono = pygame.font.SysFont("Consolas, Courier New", 12)
        self.font_metric = pygame.font.SysFont("Segoe UI, Arial", 18, bold=True)

        self.buttons: Dict[str, pygame.Rect] = {}
        self.is_running = True

        self._sprites: Dict[str, VehicleSprite] = {}
        for strategy in STRATEGIES:
            sprite = VehicleSprite(size=18)
            car_col, halo_col = self.VEHICLE_COLORS[strategy]
            sprite.CAR_COLOR = car_col
            sprite.HALO_COLOR = halo_col
            self._sprites[strategy] = sprite

        # Viewport nodes & spatial index (focus corridor for OSM, all nodes for custom)
        self._viewport_nodes: Dict[str, Tuple[float, float]] = {}
        self._viewport_adjacency: Dict[str, List[Tuple[str, int]]] = {}
        self._init_viewport_subgraph()

        self._road_renderers: Dict[str, RoadRenderer] = {}
        self._bg_cache: Dict[Tuple[str, int, Tuple[int, int]], pygame.Surface] = {}
        self._layout_panels()

    def _init_viewport_subgraph(self) -> None:
        """Restrict OSM rendering to corridor bounding box for smooth 60 FPS animation."""
        bundle = self.simulation.bundle
        all_coords = bundle.node_coords
        if bundle.network_type == "custom" or len(all_coords) <= 500:
            self._viewport_nodes = all_coords
            self._viewport_adjacency = bundle.weight_manager.adjacency
            return

        # Collect nodes traversed across initial + final routes in the simulation
        focus_nodes: Set[str] = {bundle.origin, bundle.destination}
        for strategy in STRATEGIES:
            route = self.simulation.engine.run(
                bundle.origin, bundle.destination, bundle.departure_timestamp, strategy
            )
            for e in route.traversed_edge_path:
                focus_nodes.add(str(e[0]))
                focus_nodes.add(str(e[1]))

        lats = [all_coords[n][0] for n in focus_nodes if n in all_coords]
        lons = [all_coords[n][1] for n in focus_nodes if n in all_coords]
        if not lats or not lons:
            self._viewport_nodes = all_coords
            self._viewport_adjacency = bundle.weight_manager.adjacency
            return

        pad_lat = max((max(lats) - min(lats)) * 0.25, 0.005)
        pad_lon = max((max(lons) - min(lons)) * 0.25, 0.005)
        min_lat, max_lat = min(lats) - pad_lat, max(lats) + pad_lat
        min_lon, max_lon = min(lons) - pad_lon, max(lons) + pad_lon

        sub_nodes: Dict[str, Tuple[float, float]] = {}
        for n, (lat, lon) in all_coords.items():
            if (min_lat <= lat <= max_lat and min_lon <= lon <= max_lon) or n in focus_nodes:
                sub_nodes[n] = (lat, lon)

        sub_adj: Dict[str, List[Tuple[str, int]]] = {}
        for u in sub_nodes:
            neighbors = [
                (v, k) for v, k in bundle.weight_manager.adjacency.get(u, []) if v in sub_nodes
            ]
            if neighbors:
                sub_adj[u] = neighbors

        self._viewport_nodes = sub_nodes
        self._viewport_adjacency = sub_adj

    def _layout_panels(self) -> None:
        """Recompute header, 3 equal panels, and bottom comparison rects."""
        pad = 10
        header_h = 68
        footer_h = 156

        self.header_rect = pygame.Rect(pad, pad, self.width - 2 * pad, header_h)
        mid_top = self.header_rect.bottom + pad
        mid_h = max(280, self.height - mid_top - footer_h - 2 * pad)
        self.footer_rect = pygame.Rect(pad, mid_top + mid_h + pad, self.width - 2 * pad, footer_h)

        panel_w = (self.width - 4 * pad) // 3
        telemetry_h = 128
        panel_header_h = 34

        self.panel_rects: Dict[str, pygame.Rect] = {}
        self.map_rects: Dict[str, pygame.Rect] = {}
        self.telemetry_rects: Dict[str, pygame.Rect] = {}
        self._road_renderers.clear()
        self._bg_cache.clear()

        is_geo = self.simulation.bundle.network_type == "osm"
        for idx, strategy in enumerate(STRATEGIES):
            px = pad + idx * (panel_w + pad)
            panel_rect = pygame.Rect(px, mid_top, panel_w, mid_h)
            map_rect = pygame.Rect(
                px + 4,
                mid_top + panel_header_h,
                panel_w - 8,
                max(140, mid_h - panel_header_h - telemetry_h - 4),
            )
            tel_rect = pygame.Rect(
                px + 4,
                map_rect.bottom + 4,
                panel_w - 8,
                telemetry_h - 4,
            )
            self.panel_rects[strategy] = panel_rect
            self.map_rects[strategy] = map_rect
            self.telemetry_rects[strategy] = tel_rect

            margin = 28.0 if not is_geo else 18.0
            if self._viewport_nodes:
                if is_geo:
                    hs = [pt[1] for pt in self._viewport_nodes.values()]
                    vs = [pt[0] for pt in self._viewport_nodes.values()]
                else:
                    hs = [pt[0] for pt in self._viewport_nodes.values()]
                    vs = [pt[1] for pt in self._viewport_nodes.values()]
                span_h = max(max(hs) - min(hs), 1e-6)
                span_v = max(max(vs) - min(vs), 1e-6)
                avail_w = max(map_rect.width - 2.0 * margin, 10.0)
                avail_h = max(map_rect.height - 2.0 * margin, 10.0)
                scale = min(avail_w / span_h, avail_h / span_v)
                drawn_w = int(round(span_h * scale + 2.0 * margin))
                drawn_h = int(round(span_v * scale + 2.0 * margin))
                rel_rect = pygame.Rect(
                    max(0, (map_rect.width - drawn_w) // 2),
                    max(0, (map_rect.height - drawn_h) // 2),
                    min(map_rect.width, drawn_w),
                    min(map_rect.height, drawn_h),
                )
            else:
                rel_rect = pygame.Rect(0, 0, map_rect.width, map_rect.height)
            rr = RoadRenderer(self._viewport_nodes, rel_rect, is_geographic=is_geo)
            rr.margin = margin
            rr._init_projection()
            self._road_renderers[strategy] = rr

    def _get_cached_map_surface(self, strategy: str, frame_idx: int) -> pygame.Surface:
        """Render and cache the static + speed-colored road network bitmap once per traffic frame."""
        map_rect = self.map_rects[strategy]
        key = (strategy, frame_idx, (map_rect.width, map_rect.height))
        if key in self._bg_cache:
            return self._bg_cache[key]

        surf = pygame.Surface((map_rect.width, map_rect.height))
        surf.fill(RoadRenderer.BG_COLOR)
        rr = self._road_renderers[strategy]
        realized_speeds = self.simulation.current_realized_speeds()
        bundle = self.simulation.bundle
        edge_w = 4 if bundle.network_type == "custom" else 1

        # Draw base road network colored by current realized speeds
        for u, neighbors in self._viewport_adjacency.items():
            p_u = rr.project_point(u)
            if not p_u:
                continue
            for v, k in neighbors:
                p_v = rr.project_point(v)
                if not p_v:
                    continue
                spd = realized_speeds.get((u, v, k), 30.0)
                col = rr.get_traffic_color(spd)
                pygame.draw.line(surf, col, p_u, p_v, width=edge_w)

        # Draw node dots (all nodes on custom, sparse intersections kept clean on OSM)
        if bundle.network_type == "custom":
            ys = [pt[1] for pt in self._viewport_nodes.values()]
            mid_y = (min(ys) + max(ys)) / 2.0 if ys else 0.0
            for node_id in self._viewport_nodes:
                pt = rr.project_point(node_id)
                if not pt:
                    continue
                if node_id == bundle.origin:
                    pygame.draw.circle(surf, rr.ORIGIN_COLOR, pt, 8)
                    pygame.draw.circle(surf, (255, 255, 255), pt, 3)
                elif node_id == bundle.destination:
                    pygame.draw.circle(surf, rr.DEST_COLOR, pt, 9)
                    pygame.draw.circle(surf, (255, 255, 255), pt, 4)
                else:
                    pygame.draw.circle(surf, rr.NODE_COLOR, pt, 5)
                lbl = self.font_small.render(str(node_id), True, self.TEXT_MAIN)
                ny = self._viewport_nodes[node_id][1]
                ly = pt[1] + 10 if ny > mid_y else pt[1] - 21
                surf.blit(lbl, (pt[0] - lbl.get_width() // 2, ly))
        else:
            p_o = rr.project_point(bundle.origin)
            p_d = rr.project_point(bundle.destination)
            if p_o:
                pygame.draw.circle(surf, rr.ORIGIN_COLOR, p_o, 7)
                pygame.draw.circle(surf, (255, 255, 255), p_o, 3)
            if p_d:
                pygame.draw.circle(surf, rr.DEST_COLOR, p_d, 8)
                pygame.draw.circle(surf, (255, 255, 255), p_d, 3)

        self._bg_cache[key] = surf
        return surf

    def handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.is_running = False
            elif event.type == pygame.VIDEORESIZE:
                self.width = max(960, event.w)
                self.height = max(620, event.h)
                self.screen = pygame.display.set_mode((self.width, self.height), pygame.RESIZABLE)
                self._layout_panels()
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    self.is_running = False
                elif event.key == pygame.K_SPACE:
                    self.simulation.is_paused = not self.simulation.is_paused
                elif event.key == pygame.K_r:
                    self.simulation.reset()
                    self._bg_cache.clear()
                elif event.key == pygame.K_n:
                    step_s = 2.0 if self.simulation.bundle.network_type == "custom" else 15.0
                    self.simulation.step_sim(step_s)
                elif event.key == pygame.K_1:
                    self.simulation.speed_multiplier = 0.5
                elif event.key == pygame.K_2:
                    self.simulation.speed_multiplier = 1.0
                elif event.key == pygame.K_3:
                    self.simulation.speed_multiplier = 2.0
                elif event.key in (pygame.K_4, pygame.K_5):
                    self.simulation.speed_multiplier = 5.0
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._handle_click(event.pos)

    def _handle_click(self, pos: Tuple[int, int]) -> None:
        if "play_pause" in self.buttons and self.buttons["play_pause"].collidepoint(pos):
            self.simulation.is_paused = not self.simulation.is_paused
        elif "step" in self.buttons and self.buttons["step"].collidepoint(pos):
            step_s = 2.0 if self.simulation.bundle.network_type == "custom" else 15.0
            self.simulation.step_sim(step_s)
        elif "reset" in self.buttons and self.buttons["reset"].collidepoint(pos):
            self.simulation.reset()
            self._bg_cache.clear()
        elif "spd_05" in self.buttons and self.buttons["spd_05"].collidepoint(pos):
            self.simulation.speed_multiplier = 0.5
        elif "spd_1" in self.buttons and self.buttons["spd_1"].collidepoint(pos):
            self.simulation.speed_multiplier = 1.0
        elif "spd_2" in self.buttons and self.buttons["spd_2"].collidepoint(pos):
            self.simulation.speed_multiplier = 2.0
        elif "spd_5" in self.buttons and self.buttons["spd_5"].collidepoint(pos):
            self.simulation.speed_multiplier = 5.0

    def _draw_button(self, rect: pygame.Rect, label: str, active: bool = False) -> None:
        col = self.BTN_ACTIVE if active else self.BTN_BG
        pygame.draw.rect(self.screen, col, rect, border_radius=5)
        pygame.draw.rect(self.screen, self.BORDER, rect, width=1, border_radius=5)
        txt = self.font_small.render(label, True, self.TEXT_MAIN)
        self.screen.blit(txt, txt.get_rect(center=rect.center))

    def _draw_header(self) -> None:
        r = self.header_rect
        pygame.draw.rect(self.screen, self.PANEL_BG, r, border_radius=8)
        pygame.draw.rect(self.screen, self.BORDER, r, width=1, border_radius=8)

        bundle = self.simulation.bundle
        title = self.font_title.render(bundle.title, True, self.TEXT_MAIN)
        self.screen.blit(title, (r.x + 14, r.y + 8))

        update_hit = self.simulation.update_became_valid
        status_col = self.ACCENT_RED if update_hit else self.ACCENT_GREEN
        status_txt = (
            f"TRAFFIC UPDATE ACTIVE ({bundle.congested_note})"
            if update_hit
            else "INITIAL TRAFFIC FORECAST ACTIVE (pre-update)"
        )
        if self.simulation.all_finished:
            status_col = self.ACCENT_CYAN
            status_txt = "ALL 3 JOURNEYS COMPLETE — Press R to Replay or ESC to Quit"

        sub = self.font_body.render(
            f"OD: {bundle.origin} -> {bundle.destination}   |   "
            f"Clock: +{self.simulation.sim_elapsed_s:.1f}s "
            f"({self.simulation.sim_time.strftime('%H:%M:%S')} UTC)   |   ",
            True,
            self.TEXT_MUTED,
        )
        self.screen.blit(sub, (r.x + 14, r.y + 38))
        badge_surf = self.font_small.render(status_txt, True, status_col)
        self.screen.blit(badge_surf, (r.x + 14 + sub.get_width(), r.y + 40))

        # Control buttons right-aligned
        bx = r.right - 12
        by = r.y + 18
        btn_specs = [
            ("spd_5", "5x", self.simulation.speed_multiplier == 5.0, 38),
            ("spd_2", "2x", self.simulation.speed_multiplier == 2.0, 38),
            ("spd_1", "1x", self.simulation.speed_multiplier == 1.0, 38),
            ("spd_05", "0.5x", self.simulation.speed_multiplier == 0.5, 44),
            ("reset", "Reset (R)", False, 72),
            ("step", "Step (N)", False, 66),
            ("play_pause", "Resume" if self.simulation.is_paused else "Pause (Space)", not self.simulation.is_paused, 102),
        ]
        self.buttons.clear()
        for key, label, active, bw in btn_specs:
            bx -= bw
            rect = pygame.Rect(bx, by, bw, 30)
            self.buttons[key] = rect
            self._draw_button(rect, label, active)
            bx -= 6

    def _draw_panel(self, strategy: str) -> None:
        agent: StrategyAgentState = self.simulation.agents[strategy]
        panel_rect = self.panel_rects[strategy]
        map_rect = self.map_rects[strategy]
        tel_rect = self.telemetry_rects[strategy]
        accent = self.PANEL_ACCENTS[strategy]

        # Panel frame
        pygame.draw.rect(self.screen, self.PANEL_BG, panel_rect, border_radius=8)
        border_col = self.ACCENT_GREEN if agent.arrived else accent
        pygame.draw.rect(self.screen, border_col, panel_rect, width=2 if agent.arrived else 1, border_radius=8)

        # Panel Header
        hdr = self.font_header.render(agent.display_name, True, accent)
        self.screen.blit(hdr, (panel_rect.x + 10, panel_rect.y + 8))
        st_col = self.ACCENT_GREEN if agent.arrived else (self.ACCENT_RED if agent.failed else self.TEXT_MAIN)
        st_surf = self.font_small.render(agent.status_label[:26], True, st_col)
        self.screen.blit(st_surf, (panel_rect.right - st_surf.get_width() - 10, panel_rect.y + 10))

        # Road Network Map Layer (cached bitmap + dynamic overlays)
        bg = self._get_cached_map_surface(strategy, self.simulation.active_frame_index)
        self.screen.blit(bg, map_rect.topleft)
        rr = self._road_renderers[strategy]

        def to_screen(node_id: str) -> Optional[Tuple[int, int]]:
            pt = rr.project_point(node_id)
            if pt is None:
                return None
            return (map_rect.left + pt[0], map_rect.top + pt[1])

        def draw_edges(edges: List[Edge], color: Tuple[int, int, int], width: int) -> None:
            for e in edges:
                p1, p2 = to_screen(str(e[0])), to_screen(str(e[1]))
                if p1 and p2:
                    pygame.draw.line(self.screen, color, p1, p2, width=width)

        # Remaining planned path (subtle sky-blue)
        if strategy == "static_dijkstra":
            rem_plan = agent.fixed_route_edges[max(0, agent.fixed_cursor - 1):]
        else:
            rem_plan = agent.planned_edges
        draw_edges(rem_plan, (56, 189, 248), width=2)

        # Traversed path (Indigo)
        draw_edges(agent.traversed_edges, RoadRenderer.TRAVERSED_COLOR, width=5 if self.simulation.bundle.network_type == "custom" else 3)

        # GeoPulse Candidate A (Cyan) & Candidate B (Orange) highlights
        if strategy == "geopulse_two_edge":
            if agent.candidate_a:
                draw_edges([agent.candidate_a], RoadRenderer.CANDIDATE_A_COLOR, width=6)
            if agent.candidate_b:
                draw_edges([agent.candidate_b], RoadRenderer.CANDIDATE_B_COLOR, width=6)

        # Active edge highlight
        if agent.active_edge:
            draw_edges([agent.active_edge], RoadRenderer.SELECTED_COLOR, width=5 if self.simulation.bundle.network_type == "custom" else 4)

        # Animated VehicleSprite using realized-speed progress
        sprite = self._sprites[strategy]
        if agent.active_edge and not agent.arrived:
            p1 = to_screen(str(agent.active_edge[0]))
            p2 = to_screen(str(agent.active_edge[1]))
            if p1 and p2:
                sprite.update_motion(p1, p2, agent.edge_progress)
                sprite.draw(self.screen)
        else:
            pc = to_screen(agent.current_node)
            if pc:
                sprite.current_pos = pc
                sprite.draw(self.screen)

        # Telemetry Card inside panel
        pygame.draw.rect(self.screen, self.CARD_BG, tel_rect, border_radius=6)
        pygame.draw.rect(self.screen, self.BORDER, tel_rect, width=1, border_radius=6)

        tx, ty = tel_rect.x + 10, tel_rect.y + 6
        live_t = self.simulation.live_elapsed_s(strategy)
        live_d = self.simulation.live_distance_m(strategy)
        t_surf = self.font_metric.render(f"Time: {live_t:6.1f} s", True, self.TEXT_MAIN)
        d_surf = self.font_metric.render(f"Dist: {live_d:6.0f} m", True, self.ACCENT_CYAN)
        self.screen.blit(t_surf, (tx, ty))
        self.screen.blit(d_surf, (tel_rect.right - d_surf.get_width() - 10, ty))
        ty += 24

        edge_txt = (
            f"Edge: {agent.active_edge[0]}->{agent.active_edge[1]} @ {agent.active_edge_realized_speed_kmh:.1f} km/h (realized)"
            if agent.active_edge and not agent.arrived
            else f"Node: {agent.current_node} | Edges traversed: {len(agent.traversed_edges)}"
        )
        self.screen.blit(self.font_mono.render(edge_txt[:46], True, self.TEXT_MUTED), (tx, ty))
        ty += 18

        if strategy == "static_dijkstra":
            c_txt = f"Updates Applied: 0 (Fixed) | Reroutes: 0 | Edges: {len(agent.traversed_edges)}"
        elif strategy == "dynamic_dijkstra":
            c_txt = f"Updates: {agent.prediction_updates_applied} | Dijkstra Reroutes: {agent.dijkstra_reroutes} | Edges: {len(agent.traversed_edges)}"
        else:
            c_txt = (
                f"Decisions: {agent.intersection_decisions} | 2-Edge Alt: {agent.two_edge_alternative_selections} | "
                f"Fallback: {agent.dijkstra_fallback_steps}"
            )
        self.screen.blit(self.font_small.render(c_txt[:54], True, accent), (tx, ty))
        ty += 18

        # Candidate evaluation or decision reason line
        if strategy == "geopulse_two_edge" and agent.candidate_a is not None:
            ca = f"A:{agent.candidate_a[0]}->{agent.candidate_a[1]}({agent.score_a:.1f}s)" if agent.score_a is not None else ""
            cb = (
                f"B:{agent.candidate_b[0]}->{agent.candidate_b[1]}({agent.score_b:.1f}s)"
                if agent.candidate_b is not None and agent.score_b is not None
                else "B:(forced)"
            )
            cand_line = f"{ca}  vs  {cb}  -> {agent.selected_candidate_slot}"
            self.screen.blit(self.font_mono.render(cand_line[:50], True, self.TEXT_MAIN), (tx, ty))
            ty += 17

        reason_surf = self.font_small.render(agent.decision_reason[:54], True, self.TEXT_MUTED)
        self.screen.blit(reason_surf, (tx, ty))

    def _draw_footer_comparison(self) -> None:
        r = self.footer_rect
        pygame.draw.rect(self.screen, self.PANEL_BG, r, border_radius=8)
        pygame.draw.rect(
            self.screen,
            self.ACCENT_GREEN if self.simulation.all_finished else self.BORDER,
            r,
            width=2 if self.simulation.all_finished else 1,
            border_radius=8,
        )

        x = r.x + 14
        y = r.y + 8
        heading = (
            "FINAL SIDE-BY-SIDE PERFORMANCE COMPARISON"
            if self.simulation.all_finished
            else "LIVE SIDE-BY-SIDE METRICS  (Traffic Legend: Green >=35 km/h | Amber 20-35 | Red <20 km/h | Blue=Plan | Cyan/Orange=GeoPulse A/B)"
        )
        self.screen.blit(
            self.font_header.render(
                heading, True, self.ACCENT_GREEN if self.simulation.all_finished else self.TEXT_MAIN
            ),
            (x, y),
        )
        y += 24

        # Table header scaled proportionally to fit footer width cleanly
        avail_w = max(800, r.width - 28)
        base_cols = [
            ("Strategy", 160),
            ("Status", 145),
            ("Time (s)", 85),
            ("Saved vs Static", 145),
            ("Distance (m)", 100),
            ("Edges", 60),
            ("Updates", 65),
            ("Reroutes / 2E-Alt", 125),
            ("Fallbacks / Backtracks", 145),
        ]
        total_base = sum(cw for _, cw in base_cols)
        scale = avail_w / total_base
        cols = [(name, int(cw * scale)) for name, cw in base_cols]
        cx = x
        for col_title, cw in cols:
            self.screen.blit(self.font_small.render(col_title, True, self.TEXT_MUTED), (cx, y))
            cx += cw
        y += 18
        pygame.draw.line(self.screen, self.BORDER, (x, y), (r.right - 14, y), width=1)
        y += 5

        rows = self.simulation.get_comparison_rows()
        col_widths = [cw for _, cw in cols]
        for row in rows:
            accent = self.PANEL_ACCENTS[row["strategy"]]
            saved_str = (
                f"{row['saved_vs_static_s']:+.1f}s ({row['saved_vs_static_pct']:+.1f}%)"
                if row["saved_vs_static_s"] is not None
                else ("Baseline" if row["strategy"] == "static_dijkstra" else "Pending")
            )
            reroute_alt = (
                str(row["two_edge_alt_selections"])
                if row["strategy"] == "geopulse_two_edge"
                else str(row["reroutes"])
            )
            fb_bt = f"{row['fallback_steps']} / {row['backtracking_events']}"
            vals = [
                (row["label"], col_widths[0], accent),
                (row["status"][:18], col_widths[1], self.ACCENT_GREEN if row["arrived"] else self.TEXT_MAIN),
                (f"{row['elapsed_time_s']:.2f}", col_widths[2], self.TEXT_MAIN),
                (saved_str, col_widths[3], self.ACCENT_GREEN if (row["saved_vs_static_s"] or 0) > 0 else self.TEXT_MUTED),
                (f"{row['distance_m']:.1f}", col_widths[4], self.TEXT_MAIN),
                (str(row["edges_traversed"]), col_widths[5], self.TEXT_MAIN),
                (str(row["updates_applied"]), col_widths[6], self.TEXT_MAIN),
                (reroute_alt, col_widths[7], self.TEXT_MAIN),
                (fb_bt, col_widths[8], self.TEXT_MAIN),
            ]
            cx = x
            for text, cw, col in vals:
                self.screen.blit(self.font_mono.render(text, True, col), (cx, y))
                cx += cw
            y += 22

        # Winner banner when finished
        if self.simulation.all_finished:
            completed = [row for row in rows if row["arrived"] and not row["failed"]]
            if completed:
                best_t = min(item["elapsed_time_s"] for item in completed)
                fastest_labels = " & ".join(
                    item["label"]
                    for item in completed
                    if abs(item["elapsed_time_s"] - best_t) <= 1e-6
                )
                static_row = next(row for row in rows if row["strategy"] == "static_dijkstra")
                if static_row["arrived"] and not static_row["failed"] and static_row["elapsed_time_s"] > best_t + 1e-6:
                    gain_s = static_row["elapsed_time_s"] - best_t
                    gain_pct = (gain_s / static_row["elapsed_time_s"]) * 100.0
                    summary_msg = (
                        f"Fastest: {fastest_labels} ({best_t:.2f}s)  |  "
                        f"Saved vs Static Dijkstra: {gain_s:.2f}s ({gain_pct:.1f}%)"
                    )
                else:
                    summary_msg = f"Fastest completed: {fastest_labels} ({best_t:.2f}s)"
                self.screen.blit(
                    self.font_body.render(summary_msg, True, self.ACCENT_GOLD),
                    (x, y + 4),
                )

    def render_frame(self) -> None:
        self.screen.fill(self.BG_COLOR)
        self._draw_header()
        for strategy in STRATEGIES:
            self._draw_panel(strategy)
        self._draw_footer_comparison()
        pygame.display.flip()

    def run_loop(self, max_seconds: Optional[float] = None) -> None:
        start = time.time()
        while self.is_running:
            dt = self.clock.tick(60) / 1000.0
            self.handle_events()
            self.simulation.update(dt)
            self.render_frame()
            if max_seconds is not None and (time.time() - start) >= max_seconds:
                break
        pygame.quit()
