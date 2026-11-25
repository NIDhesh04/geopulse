"""GIS-style dark-mode map projection, caching, traffic coloring, and polyline rendering."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import pygame

from src.experiments.temporal_journey import Edge, STRATEGIES
from src.pygame_simulation.temporal_comparison import StrategyAgentState, ThreeStrategySimulation
from src.pygame_simulation.vehicle_sprite import VehicleSprite


HIGHWAY_TIER: Dict[str, int] = {
    "living_street": 0,
    "residential": 0,
    "unclassified": 0,
    "tertiary_link": 1,
    "tertiary": 1,
    "secondary_link": 2,
    "secondary": 2,
    "primary_link": 3,
    "primary": 3,
    "trunk_link": 4,
    "trunk": 4,
    "motorway": 4,
}


class GISCamera:
    """2D planar camera supporting cursor-anchored zoom, click-drag pan, and bounds fitting."""

    def __init__(self, map_rect: pygame.Rect, is_geographic: bool):
        self.map_rect = map_rect
        self.is_geographic = is_geographic
        self.center_wx: float = 0.0
        self.center_wy: float = 0.0
        self.zoom: float = 1.0  # pixels per world unit (meters in OSM)
        self.min_zoom: float = 0.015 if is_geographic else 0.25
        self.max_zoom: float = 10.0 if is_geographic else 8.0
        self._default_points: List[Tuple[float, float]] = []

    def set_viewport(self, map_rect: pygame.Rect) -> None:
        self.map_rect = map_rect

    def world_to_screen(self, wx: float, wy: float) -> Tuple[int, int]:
        sx = self.map_rect.centerx + (wx - self.center_wx) * self.zoom
        sy = self.map_rect.centery + (wy - self.center_wy) * self.zoom
        return (int(round(sx)), int(round(sy)))

    def world_to_local(self, wx: float, wy: float) -> Tuple[int, int]:
        lx = self.map_rect.width * 0.5 + (wx - self.center_wx) * self.zoom
        ly = self.map_rect.height * 0.5 + (wy - self.center_wy) * self.zoom
        return (int(round(lx)), int(round(ly)))

    def screen_to_world(self, sx: int, sy: int) -> Tuple[float, float]:
        wx = self.center_wx + (sx - self.map_rect.centerx) / self.zoom
        wy = self.center_wy + (sy - self.map_rect.centery) / self.zoom
        return (wx, wy)

    def viewport_world_bounds(self, margin_px: float = 24.0) -> Tuple[float, float, float, float]:
        half_w = (self.map_rect.width * 0.5 + margin_px) / max(self.zoom, 1e-9)
        half_h = (self.map_rect.height * 0.5 + margin_px) / max(self.zoom, 1e-9)
        return (
            self.center_wx - half_w,
            self.center_wy - half_h,
            self.center_wx + half_w,
            self.center_wy + half_h,
        )

    def fit_bounds(self, world_pts: Sequence[Tuple[float, float]], padding_frac: float = 0.14) -> None:
        if not world_pts:
            return
        self._default_points = list(world_pts)
        xs = [pt[0] for pt in world_pts]
        ys = [pt[1] for pt in world_pts]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        span_x = max(max_x - min_x, 10.0)
        span_y = max(max_y - min_y, 10.0)
        avail_w = max(self.map_rect.width * (1.0 - 2.0 * padding_frac), 40.0)
        avail_h = max(self.map_rect.height * (1.0 - 2.0 * padding_frac), 40.0)
        self.zoom = max(self.min_zoom, min(self.max_zoom, min(avail_w / span_x, avail_h / span_y)))
        self.center_wx = 0.5 * (min_x + max_x)
        self.center_wy = 0.5 * (min_y + max_y)

    def reset_view(self) -> None:
        if self._default_points:
            self.fit_bounds(self._default_points)

    def zoom_at(self, screen_pos: Tuple[int, int], factor: float) -> None:
        wx_before, wy_before = self.screen_to_world(screen_pos[0], screen_pos[1])
        new_zoom = max(self.min_zoom, min(self.max_zoom, self.zoom * factor))
        if abs(new_zoom - self.zoom) <= 1e-12:
            return
        self.zoom = new_zoom
        self.center_wx = wx_before - (screen_pos[0] - self.map_rect.centerx) / self.zoom
        self.center_wy = wy_before - (screen_pos[1] - self.map_rect.centery) / self.zoom

    def pan_by_pixels(self, dx: float, dy: float) -> None:
        self.center_wx -= dx / max(self.zoom, 1e-9)
        self.center_wy -= dy / max(self.zoom, 1e-9)


def interpolate_polyline(
    pts_px: Sequence[Tuple[int, int]], progress: float
) -> Tuple[Tuple[float, float], float]:
    """Interpolate position and heading angle along a polyline for progress in [0, 1]."""
    if not pts_px:
        return ((0.0, 0.0), 0.0)
    if len(pts_px) == 1:
        return ((float(pts_px[0][0]), float(pts_px[0][1])), 0.0)

    p = max(0.0, min(1.0, float(progress)))
    seg_lens: List[float] = []
    total_len = 0.0
    for (x1, y1), (x2, y2) in zip(pts_px, pts_px[1:]):
        seg = math.hypot(x2 - x1, y2 - y1)
        seg_lens.append(seg)
        total_len += seg

    if total_len <= 1e-6:
        return ((float(pts_px[0][0]), float(pts_px[0][1])), 0.0)

    target = p * total_len
    accum = 0.0
    for idx, seg_len in enumerate(seg_lens):
        x1, y1 = pts_px[idx]
        x2, y2 = pts_px[idx + 1]
        if accum + seg_len >= target - 1e-9 or idx == len(seg_lens) - 1:
            local_t = (target - accum) / seg_len if seg_len > 1e-9 else 1.0
            local_t = max(0.0, min(1.0, local_t))
            px = x1 + local_t * (x2 - x1)
            py = y1 + local_t * (y2 - y1)
            heading = math.atan2(y2 - y1, x2 - x1) if seg_len > 1e-9 else 0.0
            return ((px, py), heading)
        accum += seg_len

    last = pts_px[-1]
    prev = pts_px[-2]
    return ((float(last[0]), float(last[1])), math.atan2(last[1] - prev[1], last[0] - prev[0]))


def _offset_polyline(
    pts_px: Sequence[Tuple[int, int]], offset_px: float
) -> List[Tuple[int, int]]:
    """Apply small perpendicular visual offset so overlapping strategy routes remain visible."""
    if abs(offset_px) <= 1e-6 or len(pts_px) < 2:
        return list(pts_px)
    out: List[Tuple[int, int]] = []
    n = len(pts_px)
    for i, (x, y) in enumerate(pts_px):
        if i == 0:
            dx, dy = pts_px[1][0] - x, pts_px[1][1] - y
        elif i == n - 1:
            dx, dy = x - pts_px[i - 1][0], y - pts_px[i - 1][1]
        else:
            dx, dy = pts_px[i + 1][0] - pts_px[i - 1][0], pts_px[i + 1][1] - pts_px[i - 1][1]
        length = math.hypot(dx, dy)
        if length > 1e-6:
            nx, ny = -dy / length, dx / length
            out.append((int(round(x + nx * offset_px)), int(round(y + ny * offset_px))))
        else:
            out.append((x, y))
    return out


class GISMapRenderer:
    """Renders dark-mode GIS road layers, traffic coverage, 3 routes, and polyline-steered vehicles."""

    MAP_BG = (11, 17, 30)
    GRID_LINE = (20, 30, 48)

    # Traffic colors for dynamic-sensor observed edges
    TRAFFIC_FREE = (34, 197, 94)      # Green
    TRAFFIC_MOD = (245, 158, 11)      # Yellow / Amber
    TRAFFIC_HEAVY = (239, 68, 68)     # Red

    # Static fallback / unobserved road hierarchy colors (distinct grey/slate shades)
    FALLBACK_TIER_COLORS = {
        0: (42, 54, 76),     # residential / unclassified / living_street
        1: (66, 82, 108),    # tertiary
        2: (88, 106, 134),   # secondary
        3: (116, 134, 162),  # primary
        4: (138, 156, 184),  # trunk / motorway
    }

    # Route colors & visual offsets
    ROUTE_STYLE = {
        "static_dijkstra": ((59, 130, 246), -3.0),     # Royal Blue
        "dynamic_dijkstra": ((245, 158, 11), 3.0),     # Amber Gold
        "geopulse_two_edge": ((16, 185, 129), 0.0),    # Emerald Green
    }

    CAND_A_COLOR = (6, 182, 212)      # Cyan
    CAND_B_COLOR = (244, 114, 182)    # Pink/Magenta so distinct from Amber Dynamic route
    ORIGIN_COLOR = (34, 197, 94)
    DEST_COLOR = (250, 204, 21)

    def __init__(self, simulation: ThreeStrategySimulation, map_rect: pygame.Rect):
        self.simulation = simulation
        self.bundle = simulation.bundle
        self.is_geo = self.bundle.network_type == "osm"
        self.camera = GISCamera(map_rect, is_geographic=self.is_geo)

        self.font_label = pygame.font.SysFont("Segoe UI, Arial", 11)
        self.font_badge = pygame.font.SysFont("Segoe UI, Arial", 11, bold=True)
        self.font_small = pygame.font.SysFont("Segoe UI, Arial", 10)

        self._sprites: Dict[str, VehicleSprite] = {
            "static_dijkstra": self._make_sprite((59, 130, 246), (147, 197, 253, 90)),
            "dynamic_dijkstra": self._make_sprite((245, 158, 11), (253, 224, 71, 90)),
            "geopulse_two_edge": self._make_sprite((16, 185, 129), (110, 231, 183, 95)),
        }

        self._lat0 = 0.0
        self._lon0 = 0.0
        self._m_per_deg_lat = 111132.92
        self._m_per_deg_lon = 111412.84
        self._node_world: Dict[str, Tuple[float, float]] = {}
        self._edge_world: Dict[Edge, List[Tuple[float, float]]] = {}
        # Sorted draw records: (tier, is_dynamic, edge, name, world_pts, min_x, min_y, max_x, max_y)
        self._draw_records: List[
            Tuple[int, bool, Edge, str, List[Tuple[float, float]], float, float, float, float]
        ] = []
        self._init_world_geometry()

        self._base_cache_key: Optional[Tuple[Any, ...]] = None
        self._base_cache_surf: Optional[pygame.Surface] = None
        self.show_all_routes: bool = True
        self.fit_corridor_view()

    @staticmethod
    def _make_sprite(car_col: Tuple[int, int, int], halo_col: Tuple[int, int, int, int]) -> VehicleSprite:
        sp = VehicleSprite(size=18)
        sp.CAR_COLOR = car_col
        sp.HALO_COLOR = halo_col
        return sp

    def _to_world(self, coord: Tuple[float, float]) -> Tuple[float, float]:
        if self.is_geo:
            lat, lon = coord
            return (
                (lon - self._lon0) * self._m_per_deg_lon,
                -(lat - self._lat0) * self._m_per_deg_lat,
            )
        return (coord[0] - self._lon0, coord[1] - self._lat0)

    def _init_world_geometry(self) -> None:
        coords = self.bundle.node_coords
        if coords:
            if self.is_geo:
                lats = [pt[0] for pt in coords.values()]
                lons = [pt[1] for pt in coords.values()]
                self._lat0 = 0.5 * (min(lats) + max(lats))
                self._lon0 = 0.5 * (min(lons) + max(lons))
                self._m_per_deg_lon = 111412.84 * max(0.1, math.cos(math.radians(self._lat0)))
            else:
                xs = [pt[0] for pt in coords.values()]
                ys = [pt[1] for pt in coords.values()]
                self._lon0 = 0.5 * (min(xs) + max(xs))
                self._lat0 = 0.5 * (min(ys) + max(ys))

        for node_id, pt in coords.items():
            self._node_world[node_id] = self._to_world(pt)

        records = []
        for edge in self.bundle.weight_manager.edge_lengths:
            raw_pts = self.bundle.edge_geometries.get(edge)
            if not raw_pts:
                u_pt = coords.get(str(edge[0]))
                v_pt = coords.get(str(edge[1]))
                if u_pt and v_pt:
                    raw_pts = [u_pt, v_pt]
                else:
                    continue
            w_pts = [self._to_world(pt) for pt in raw_pts]
            self._edge_world[edge] = w_pts
            xs = [p[0] for p in w_pts]
            ys = [p[1] for p in w_pts]
            hw = self.bundle.edge_highways.get(edge, "unclassified")
            tier = HIGHWAY_TIER.get(hw, 0)
            is_dyn = edge in self.bundle.dynamic_edges
            name = self.bundle.edge_names.get(edge, "")
            records.append(
                (tier, is_dyn, edge, name, w_pts, min(xs), min(ys), max(xs), max(ys))
            )

        # Draw minor/unobserved roads first, major & sensor-observed roads on top
        records.sort(key=lambda item: (item[0], 1 if item[1] else 0))
        self._draw_records = records

    def fit_corridor_view(self) -> None:
        """Fit initial camera onto the active corridor (union of initial + executed paths)."""
        pts: List[Tuple[float, float]] = []
        if self.bundle.origin in self._node_world:
            pts.append(self._node_world[self.bundle.origin])
        if self.bundle.destination in self._node_world:
            pts.append(self._node_world[self.bundle.destination])

        for agent in self.simulation.agents.values():
            for e in list(agent.fixed_route_edges) + list(agent.planned_edges) + list(agent.traversed_edges):
                pts.extend(self._edge_world.get(e, ()))

        if not pts:
            pts = list(self._node_world.values())
        self.camera.fit_bounds(pts, padding_frac=0.14 if self.is_geo else 0.12)
        self.invalidate_cache()

    def set_viewport(self, map_rect: pygame.Rect) -> None:
        self.camera.set_viewport(map_rect)
        self.invalidate_cache()

    def invalidate_cache(self) -> None:
        self._base_cache_key = None

    def _classify_traffic_color(
        self,
        edge: Edge,
        realized_speeds: Dict[Edge, float],
        frame_valid_dyn: Optional[Set[Edge]] = None,
    ) -> Tuple[int, int, int]:
        if edge not in self.bundle.dynamic_edges:
            return self.FALLBACK_TIER_COLORS[HIGHWAY_TIER.get(self.bundle.edge_highways.get(edge, ""), 0)]
        if frame_valid_dyn is not None and edge not in frame_valid_dyn:
            return (100, 116, 139)  # missing/invalid sensor in current frame -> static fallback grey

        spd = realized_speeds.get(edge)
        if spd is None:
            return (100, 116, 139)
        free_flow = max(self.bundle.weight_manager.edge_static_speeds.get(edge, 30.0), 1.0)
        ratio = spd / free_flow
        if spd >= 35.0 or ratio >= 0.85:
            return self.TRAFFIC_FREE
        if spd >= 20.0 or ratio >= 0.55:
            return self.TRAFFIC_MOD
        return self.TRAFFIC_HEAVY

    def _get_base_surface(self, drag_preview: Tuple[int, int] = (0, 0)) -> Tuple[pygame.Surface, Tuple[int, int]]:
        """Render or reuse the cached dark-mode GIS road & traffic base layer."""
        rect = self.camera.map_rect
        frame_idx = self.simulation.active_frame_index
        key = (
            rect.width,
            rect.height,
            round(self.camera.center_wx, 2),
            round(self.camera.center_wy, 2),
            round(self.camera.zoom, 6),
            frame_idx,
        )
        if self._base_cache_surf is not None and (drag_preview != (0, 0) or self._base_cache_key == key):
            return self._base_cache_surf, drag_preview

        surf = pygame.Surface((rect.width, rect.height))
        surf.fill(self.MAP_BG)

        min_wx, min_wy, max_wx, max_wy = self.camera.viewport_world_bounds()
        realized_speeds = self.simulation.current_realized_speeds()
        frame = self.simulation.engine.frames[frame_idx]
        _, _, valid_dyn_edges = self.bundle.weight_manager.build_scenario_weights(frame.realized_speeds)
        zoom = self.camera.zoom

        # Subtle geographic coordinate graticule
        grid_step_m = 1000.0 if (zoom < 0.08) else (500.0 if zoom < 0.25 else 200.0)
        if not self.is_geo:
            grid_step_m = 100.0
        gx0 = math.floor(min_wx / grid_step_m) * grid_step_m
        gy0 = math.floor(min_wy / grid_step_m) * grid_step_m
        gx = gx0
        while gx <= max_wx:
            lx, _ = self.camera.world_to_local(gx, 0.0)
            pygame.draw.line(surf, self.GRID_LINE, (lx, 0), (lx, rect.height), 1)
            gx += grid_step_m
        gy = gy0
        while gy <= max_wy:
            _, ly = self.camera.world_to_local(0.0, gy)
            pygame.draw.line(surf, self.GRID_LINE, (0, ly), (rect.width, ly), 1)
            gy += grid_step_m

        # Filter edges inside viewport
        visible = [
            rec
            for rec in self._draw_records
            if not (rec[7] < min_wx or rec[5] > max_wx or rec[8] < min_wy or rec[6] > max_wy)
        ]

        # Draw edges by hierarchy & dynamic speed
        label_candidates: List[Tuple[int, str, Tuple[int, int]]] = []
        drawn_names: Set[str] = set()
        skip_minor = self.is_geo and len(visible) > 22000 and zoom < 0.04

        for tier, is_dyn, edge, name, w_pts, ex0, ey0, ex1, ey1 in visible:
            if skip_minor and tier == 0 and not is_dyn:
                continue
            pts_px = [self.camera.world_to_local(wx, wy) for wx, wy in w_pts]
            if len(pts_px) < 2:
                continue
            col = self._classify_traffic_color(edge, realized_speeds, valid_dyn_edges)
            base_w = 1 + tier if self.is_geo else 4
            if zoom >= 0.25 and self.is_geo:
                base_w = min(6, base_w + 1)
            if is_dyn and self.is_geo:
                base_w = max(base_w, 3)

            if len(pts_px) == 2:
                pygame.draw.line(surf, col, pts_px[0], pts_px[1], width=base_w)
            else:
                pygame.draw.lines(surf, col, False, pts_px, width=base_w)

            # Collect crisp road name labels on zoomed-in major/secondary/tertiary links
            if name and (not self.is_geo or (tier >= 1 and zoom >= 0.08)):
                if name not in drawn_names:
                    dx = pts_px[-1][0] - pts_px[0][0]
                    dy = pts_px[-1][1] - pts_px[0][1]
                    if dx * dx + dy * dy >= (55 * 55 if self.is_geo else 30 * 30):
                        mid = pts_px[len(pts_px) // 2]
                        if 30 <= mid[0] <= rect.width - 90 and 25 <= mid[1] <= rect.height - 40:
                            label_candidates.append((tier, name, mid))
                            drawn_names.add(name)

        # Draw junction dots when zoomed in or on custom grid
        if not self.is_geo or zoom >= 0.22:
            node_r = 5 if not self.is_geo else 2
            for node_id, (wx, wy) in self._node_world.items():
                if min_wx <= wx <= max_wx and min_wy <= wy <= max_wy:
                    lx, ly = self.camera.world_to_local(wx, wy)
                    pygame.draw.circle(surf, (130, 145, 170), (lx, ly), node_r)
                    if not self.is_geo:
                        lbl = self.font_badge.render(str(node_id), True, (226, 232, 240))
                        surf.blit(lbl, (lx - lbl.get_width() // 2, ly - 18))

        # Place up to 16 non-overlapping road labels
        placed_rects: List[pygame.Rect] = []
        label_candidates.sort(key=lambda item: -item[0])
        for _, name, mid in label_candidates[:60]:
            if len(placed_rects) >= 16:
                break
            txt = self.font_small.render(name[:24], True, (203, 213, 225))
            box = txt.get_rect(center=(mid[0], mid[1] - 9)).inflate(6, 2)
            if any(box.colliderect(other) for other in placed_rects):
                continue
            pygame.draw.rect(surf, (15, 23, 42), box, border_radius=3)
            surf.blit(txt, txt.get_rect(center=box.center))
            placed_rects.append(box)

        self._base_cache_key = key
        self._base_cache_surf = surf
        return surf, (0, 0)

    def _edge_screen_points(self, edge: Edge, offset_px: float = 0.0) -> List[Tuple[int, int]]:
        w_pts = self._edge_world.get(edge)
        if not w_pts:
            u_w = self._node_world.get(str(edge[0]))
            v_w = self._node_world.get(str(edge[1]))
            if not u_w or not v_w:
                return []
            w_pts = [u_w, v_w]
        pts = [self.camera.world_to_screen(wx, wy) for wx, wy in w_pts]
        return _offset_polyline(pts, offset_px)

    @staticmethod
    def _draw_dashed_polyline(
        surface: pygame.Surface,
        color: Tuple[int, int, int],
        pts: Sequence[Tuple[int, int]],
        width: int = 2,
        dash_len: float = 8.0,
    ) -> None:
        if len(pts) < 2:
            return
        draw_on = True
        rem = dash_len
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            dx, dy = x2 - x1, y2 - y1
            seg = math.hypot(dx, dy)
            if seg <= 1e-3:
                continue
            pos = 0.0
            while pos < seg:
                step = min(rem, seg - pos)
                t0 = pos / seg
                t1 = (pos + step) / seg
                if draw_on:
                    pygame.draw.line(
                        surface,
                        color,
                        (int(round(x1 + dx * t0)), int(round(y1 + dy * t0))),
                        (int(round(x1 + dx * t1)), int(round(y1 + dy * t1))),
                        width=width,
                    )
                pos += step
                rem -= step
                if rem <= 1e-3:
                    draw_on = not draw_on
                    rem = dash_len

    def _draw_route_layers(self, surface: pygame.Surface) -> None:
        strategies_to_draw = (
            STRATEGIES if self.show_all_routes else ("geopulse_two_edge",)
        )

        # 1. Remaining planned routes (dashed)
        for strategy in strategies_to_draw:
            agent = self.simulation.agents[strategy]
            color, offset = self.ROUTE_STYLE[strategy]
            dim_col = (
                max(20, int(color[0] * 0.65)),
                max(20, int(color[1] * 0.65)),
                max(20, int(color[2] * 0.65)),
            )
            rem = (
                agent.fixed_route_edges[max(0, agent.fixed_cursor - 1):]
                if strategy == "static_dijkstra"
                else agent.planned_edges
            )
            for edge in rem:
                pts = self._edge_screen_points(edge, offset)
                self._draw_dashed_polyline(surface, dim_col, pts, width=2)

        # 2. Completed routes (solid bright)
        for strategy in strategies_to_draw:
            agent = self.simulation.agents[strategy]
            color, offset = self.ROUTE_STYLE[strategy]
            for edge in agent.traversed_edges:
                pts = self._edge_screen_points(edge, offset)
                if len(pts) >= 2:
                    pygame.draw.lines(surface, color, False, pts, width=4)

        # 3. GeoPulse Candidate A & B highlights ahead of GeoPulse vehicle
        geo = self.simulation.agents["geopulse_two_edge"]
        if not geo.arrived:
            for cand, col, tag in (
                (geo.candidate_a, self.CAND_A_COLOR, "A"),
                (geo.candidate_b, self.CAND_B_COLOR, "B"),
            ):
                if cand is None:
                    continue
                pts = self._edge_screen_points(cand, 0.0)
                if len(pts) >= 2:
                    pygame.draw.lines(surface, col, False, pts, width=6)
                    end_pt = pts[-1]
                    pygame.draw.circle(surface, col, end_pt, 9)
                    tag_s = self.font_badge.render(tag, True, (15, 23, 42))
                    surface.blit(tag_s, tag_s.get_rect(center=end_pt))

        # 4. Active edges + next junction rings
        for strategy in strategies_to_draw:
            agent = self.simulation.agents[strategy]
            color, offset = self.ROUTE_STYLE[strategy]
            if agent.active_edge and not agent.arrived:
                pts = self._edge_screen_points(agent.active_edge, offset)
                if len(pts) >= 2:
                    pygame.draw.lines(surface, color, False, pts, width=5)
                nj = self._node_world.get(agent.next_junction)
                if nj:
                    nj_px = self.camera.world_to_screen(*nj)
                    pygame.draw.circle(surface, color, nj_px, 7, width=2)

    def _draw_markers_and_vehicles(self, surface: pygame.Surface) -> None:
        # Origin & Destination pins
        for node_id, col, tag in (
            (self.bundle.origin, self.ORIGIN_COLOR, "O"),
            (self.bundle.destination, self.DEST_COLOR, "D"),
        ):
            w_pt = self._node_world.get(node_id)
            if not w_pt:
                continue
            px = self.camera.world_to_screen(*w_pt)
            pygame.draw.circle(surface, (15, 23, 42), px, 13)
            pygame.draw.circle(surface, col, px, 11)
            t_surf = self.font_badge.render(tag, True, (15, 23, 42))
            surface.blit(t_surf, t_surf.get_rect(center=px))

        # Vehicles steered along actual edge polyline geometry
        for strategy in STRATEGIES:
            agent: StrategyAgentState = self.simulation.agents[strategy]
            sprite = self._sprites[strategy]
            _, offset = self.ROUTE_STYLE[strategy]
            if agent.active_edge and not agent.arrived:
                pts = self._edge_screen_points(agent.active_edge, offset)
                pos, heading = interpolate_polyline(pts, agent.edge_progress)
                sprite.current_pos = pos
                sprite.heading_rad = heading
                sprite.draw(surface)
            else:
                w_pt = self._node_world.get(agent.current_node)
                if w_pt:
                    sx, sy = self.camera.world_to_screen(*w_pt)
                    sprite.current_pos = (sx + offset, sy + offset * 0.5)
                    sprite.draw(surface)

    def _draw_map_overlays(self, surface: pygame.Surface) -> None:
        rect = self.camera.map_rect

        # Top-left floating Legend card
        leg = pygame.Rect(rect.x + 12, rect.y + 12, 272, 138)
        overlay = pygame.Surface((leg.width, leg.height), pygame.SRCALPHA)
        overlay.fill((13, 20, 34, 215))
        surface.blit(overlay, leg.topleft)
        pygame.draw.rect(surface, (56, 72, 102), leg, width=1, border_radius=6)

        lx, ly = leg.x + 10, leg.y + 8
        surface.blit(self.font_badge.render("TRAFFIC & ROUTES LEGEND", True, (248, 250, 252)), (lx, ly))
        ly += 19
        dyn_total = len(self.bundle.dynamic_edges)
        static_total = len(self.bundle.weight_manager.edge_lengths) - dyn_total
        items = [
            (self.TRAFFIC_FREE, "Free-Flow (Observed)"),
            (self.TRAFFIC_MOD, "Moderate Congestion"),
            (self.TRAFFIC_HEAVY, "Heavy Congestion"),
            ((100, 116, 139), f"No Sensor / Static ({static_total:,} edges)"),
        ]
        for col, text in items:
            pygame.draw.line(surface, col, (lx, ly + 6), (lx + 18, ly + 6), width=3)
            surface.blit(self.font_small.render(text, True, (203, 213, 225)), (lx + 24, ly))
            ly += 15

        ly += 4
        routes = [
            (self.ROUTE_STYLE["static_dijkstra"][0], "Static Dijkstra"),
            (self.ROUTE_STYLE["dynamic_dijkstra"][0], "Dynamic Dijkstra"),
            (self.ROUTE_STYLE["geopulse_two_edge"][0], "GeoPulse"),
        ]
        rx = lx
        for col, text in routes:
            pygame.draw.circle(surface, col, (rx + 4, ly + 6), 4)
            s = self.font_small.render(text, True, (226, 232, 240))
            surface.blit(s, (rx + 11, ly))
            rx += s.get_width() + 18

        ly += 16
        cand_txt = self.font_small.render(
            f"GeoPulse Candidates: A (Cyan) | B (Pink) | {dyn_total} dynamic links",
            True,
            (148, 163, 184),
        )
        surface.blit(cand_txt, (lx, ly))

        # Bottom-left Metric Scale Bar + North Arrow
        target_px = 95.0
        raw_m = target_px / max(self.camera.zoom, 1e-6)
        nice_steps = [25, 50, 100, 250, 500, 1000, 2000, 5000, 10000]
        bar_m = min(nice_steps, key=lambda v: abs(v - raw_m))
        bar_px = max(35, min(150, int(round(bar_m * self.camera.zoom))))
        bar_label = f"{bar_m // 1000} km" if bar_m >= 1000 else f"{bar_m} m"
        if not self.is_geo:
            bar_label = f"{bar_m} units"

        sb_rect = pygame.Rect(rect.x + 12, rect.bottom - 42, bar_px + 72, 30)
        sb_bg = pygame.Surface((sb_rect.width, sb_rect.height), pygame.SRCALPHA)
        sb_bg.fill((13, 20, 34, 210))
        surface.blit(sb_bg, sb_rect.topleft)
        pygame.draw.rect(surface, (56, 72, 102), sb_rect, width=1, border_radius=5)

        bx, by = sb_rect.x + 10, sb_rect.y + 18
        pygame.draw.line(surface, (248, 250, 252), (bx, by), (bx + bar_px, by), 2)
        pygame.draw.line(surface, (248, 250, 252), (bx, by - 4), (bx, by + 4), 2)
        pygame.draw.line(surface, (248, 250, 252), (bx + bar_px, by - 4), (bx + bar_px, by + 4), 2)
        surface.blit(self.font_small.render(bar_label, True, (226, 232, 240)), (bx + 4, sb_rect.y + 3))

        # North indicator
        nx_c, ny_c = sb_rect.right - 22, sb_rect.centery
        pygame.draw.polygon(
            surface,
            (56, 189, 248),
            [(nx_c, ny_c - 9), (nx_c - 5, ny_c + 5), (nx_c, ny_c + 2), (nx_c + 5, ny_c + 5)],
        )
        surface.blit(self.font_small.render("N", True, (248, 250, 252)), (nx_c + 8, ny_c - 7))

    def draw(self, surface: pygame.Surface, drag_preview: Tuple[int, int] = (0, 0)) -> None:
        rect = self.camera.map_rect
        prev_clip = surface.get_clip()
        surface.set_clip(rect)
        surface.fill(self.MAP_BG, rect)

        base_surf, offset = self._get_base_surface(drag_preview=drag_preview)
        surface.blit(base_surf, (rect.x + offset[0], rect.y + offset[1]))

        if drag_preview == (0, 0):
            self._draw_route_layers(surface)
            self._draw_markers_and_vehicles(surface)
        self._draw_map_overlays(surface)

        surface.set_clip(prev_clip)
        pygame.draw.rect(surface, (56, 72, 102), rect, width=1)
