"""
GeoPulse Pygame Road Network Renderer

Handles spatial projection and rendering of:
- Road segments colored by traffic congestion speed.
- Candidate outgoing edges A (Cyan) and B (Orange).
- Selected edge (Neon Green).
- Traversed historical path (Indigo/Blue).
- Intersections, origin, destination, and decision nodes.
"""

from typing import Dict, List, Tuple, Set, Optional, Any
import math
try:
    import pygame
except ImportError:
    # Create a minimal stub for pygame used in tests
    class _PygameStub:
        def __getattr__(self, name):
            # Return a dummy function or value
            def dummy(*args, **kwargs):
                return None
            return dummy
    pygame = _PygameStub()


class RoadRenderer:
    """Renders the road network topology, congestion states, and candidate edges."""

    # Color palette
    BG_COLOR = (15, 23, 42)          # Slate 900
    GRID_COLOR = (30, 41, 59)        # Slate 800
    ROAD_STATIC = (71, 85, 105)      # Slate 600

    # Traffic congestion speeds
    COLOR_FREE_FLOW = (34, 197, 94)  # Emerald 500 (>= 35 km/h)
    COLOR_MODERATE = (245, 158, 11)  # Amber 500 (20 - 35 km/h)
    COLOR_CONGESTED = (239, 68, 68)  # Red 500 (< 20 km/h)

    # Candidate Highlights
    CANDIDATE_A_COLOR = (6, 182, 212)    # Cyan 500
    CANDIDATE_B_COLOR = (249, 115, 22)   # Orange 500
    SELECTED_COLOR = (16, 185, 129)      # Green 500
    TRAVERSED_COLOR = (99, 102, 241)     # Indigo 500

    # Node markers
    ORIGIN_COLOR = (34, 197, 94)
    DEST_COLOR = (234, 179, 8)
    NODE_COLOR = (148, 163, 184)
    CURRENT_NODE_COLOR = (244, 63, 94)

    def __init__(
        self,
        node_coords: Dict[str, Tuple[float, float]],
        canvas_rect: pygame.Rect,
        is_geographic: bool = False
    ):
        self.node_coords = node_coords
        self.canvas_rect = canvas_rect
        self.is_geographic = is_geographic

        # Compute scaling parameters
        self._init_projection()

    def _init_projection(self):
        """Calculates affine transformation to fit nodes neatly within canvas_rect."""
        if not self.node_coords:
            self.scale_x = self.scale_y = 1.0
            self.offset_x = self.offset_y = 0.0
            return

        xs = [pt[0] for pt in self.node_coords.values()]
        ys = [pt[1] for pt in self.node_coords.values()]

        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        span_x = max(max_x - min_x, 1e-6)
        span_y = max(max_y - min_y, 1e-6)

        margin = 40.0
        avail_w = max(self.canvas_rect.width - 2 * margin, 10.0)
        avail_h = max(self.canvas_rect.height - 2 * margin, 10.0)

        if self.is_geographic:
            # Lat/lon: x is lat (vertical), y is lon (horizontal) or vice versa
            # Typically lat in [20.2, 20.4], lon in [85.7, 85.9]
            # Standard: lon -> screen X, lat -> screen Y (inverted)
            min_lat, max_lat = min_x, max_x
            min_lon, max_lon = min_y, max_y

            scale = min(avail_w / (max_lon - min_lon), avail_h / (max_lat - min_lat))
            self.scale_lon = scale
            self.scale_lat = scale
            self.min_lon = min_lon
            self.min_lat = min_lat
            self.margin = margin
        else:
            # Custom Cartesian plane
            scale = min(avail_w / span_x, avail_h / span_y)
            self.scale_x = scale
            self.scale_y = scale
            self.min_x = min_x
            self.min_y = min_y
            self.margin = margin

    def project_point(self, node_id: str) -> Optional[Tuple[int, int]]:
        """Maps a node_id to integer screen pixel coordinates."""
        if node_id not in self.node_coords:
            return None

        pt = self.node_coords[node_id]

        if self.is_geographic:
            lat, lon = pt
            px = int(self.canvas_rect.left + self.margin + (lon - self.min_lon) * self.scale_lon)
            # Invert latitude so North is top
            py = int(self.canvas_rect.bottom - self.margin - (lat - self.min_lat) * self.scale_lat)
            return (px, py)
        else:
            x, y = pt
            px = int(self.canvas_rect.left + self.margin + (x - self.min_x) * self.scale_x)
            py = int(self.canvas_rect.top + self.margin + (y - self.min_y) * self.scale_y)
            return (px, py)

    def get_traffic_color(self, speed_kmh: float) -> Tuple[int, int, int]:
        """Maps speed to traffic congestion color."""
        if speed_kmh >= 35.0:
            return self.COLOR_FREE_FLOW
        elif speed_kmh >= 20.0:
            return self.COLOR_MODERATE
        else:
            return self.COLOR_CONGESTED

    def draw_network(
        self,
        surface: pygame.Surface,
        adjacency: Dict[str, List[Tuple[str, int]]],
        edge_speeds: Dict[Tuple[str, str, int], float],
        source_node: str,
        destination_node: str,
        current_node: Optional[str] = None,
        candidate_a: Optional[Tuple[str, str, int]] = None,
        candidate_b: Optional[Tuple[str, str, int]] = None,
        selected_edge: Optional[Tuple[str, str, int]] = None,
        traversed_edges: Optional[List[Tuple[str, str, int]]] = None
    ):
        """Draws the complete road network layer."""
        # 1. Base road network lines
        drawn_edges = set()
        for u, neighbors in adjacency.items():
            p_u = self.project_point(u)
            if not p_u:
                continue

            for v, k in neighbors:
                p_v = self.project_point(v)
                if not p_v:
                    continue

                edge_key = (u, v, k)
                drawn_edges.add(edge_key)

                spd = edge_speeds.get(edge_key, 30.0)
                col = self.get_traffic_color(spd)
                pygame.draw.line(surface, col, p_u, p_v, width=3)

        # 2. Draw traversed historical path
        if traversed_edges:
            for e in traversed_edges:
                p_u = self.project_point(e[0])
                p_v = self.project_point(e[1])
                if p_u and p_v:
                    pygame.draw.line(surface, self.TRAVERSED_COLOR, p_u, p_v, width=5)

        # 3. Highlight Candidate Edge A (Cyan)
        if candidate_a:
            p_u = self.project_point(candidate_a[0])
            p_v = self.project_point(candidate_a[1])
            if p_u and p_v:
                pygame.draw.line(surface, self.CANDIDATE_A_COLOR, p_u, p_v, width=7)
                pygame.draw.circle(surface, self.CANDIDATE_A_COLOR, p_v, 8)

        # 4. Highlight Candidate Edge B (Orange)
        if candidate_b:
            p_u = self.project_point(candidate_b[0])
            p_v = self.project_point(candidate_b[1])
            if p_u and p_v:
                pygame.draw.line(surface, self.CANDIDATE_B_COLOR, p_u, p_v, width=7)
                pygame.draw.circle(surface, self.CANDIDATE_B_COLOR, p_v, 8)

        # 5. Highlight Selected Edge (Green glow)
        if selected_edge:
            p_u = self.project_point(selected_edge[0])
            p_v = self.project_point(selected_edge[1])
            if p_u and p_v:
                pygame.draw.line(surface, self.SELECTED_COLOR, p_u, p_v, width=6)

        # 6. Draw intersection nodes
        for node_id in self.node_coords:
            pt = self.project_point(node_id)
            if not pt:
                continue

            if node_id == source_node:
                pygame.draw.circle(surface, self.ORIGIN_COLOR, pt, 9)
                pygame.draw.circle(surface, (255, 255, 255), pt, 4)
            elif node_id == destination_node:
                pygame.draw.circle(surface, self.DEST_COLOR, pt, 11)
                pygame.draw.circle(surface, (255, 255, 255), pt, 5)
            elif node_id == current_node:
                pygame.draw.circle(surface, self.CURRENT_NODE_COLOR, pt, 9)
                pygame.draw.circle(surface, (255, 255, 255), pt, 4)
            else:
                pygame.draw.circle(surface, self.NODE_COLOR, pt, 4)
