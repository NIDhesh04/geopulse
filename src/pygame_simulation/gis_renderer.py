"""Phase 6.1 GIS-style dark-mode Pygame master window & inspector panels."""

from __future__ import annotations

import os
import time
from typing import Dict, List, Optional, Tuple

import pygame

from src.experiments.temporal_journey import STRATEGIES
from src.pygame_simulation.gis_map import GISMapRenderer
from src.pygame_simulation.temporal_comparison import StrategyAgentState, ThreeStrategySimulation


class GISNavigationRenderer:
    """Modern dark-mode GIS navigation interface for synchronized 3-strategy simulation."""

    BG_COLOR = (10, 15, 28)
    PANEL_BG = (17, 24, 39)
    CARD_BG = (26, 35, 54)
    BORDER = (51, 65, 85)
    TEXT_MAIN = (248, 250, 252)
    TEXT_MUTED = (148, 163, 184)
    BTN_BG = (38, 50, 72)
    BTN_ACTIVE = (37, 99, 235)

    ACCENT_BLUE = (59, 130, 246)
    ACCENT_AMBER = (245, 158, 11)
    ACCENT_GREEN = (16, 185, 129)
    ACCENT_CYAN = (6, 182, 212)
    ACCENT_PINK = (244, 114, 182)
    ACCENT_RED = (239, 68, 68)
    ACCENT_GOLD = (250, 204, 21)

    STRATEGY_COLORS = {
        "static_dijkstra": ACCENT_BLUE,
        "dynamic_dijkstra": ACCENT_AMBER,
        "geopulse_two_edge": ACCENT_GREEN,
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

        info = pygame.display.Info()
        self._desktop_w = info.current_w if info.current_w > 0 else 1440
        self._desktop_h = info.current_h if info.current_h > 0 else 860
        if window_size is not None:
            self.width, self.height = int(window_size[0]), int(window_size[1])
        elif self.headless:
            self.width, self.height = 1440, 860
        else:
            self.width = max(1120, min(1540, self._desktop_w - 60))
            self.height = max(680, min(900, self._desktop_h - 80))

        self._windowed_size = (self.width, self.height)
        self.is_fullscreen = False
        pygame.display.set_caption(
            "GeoPulse GIS Navigation — Synchronized Static vs Dynamic vs GeoPulse Simulation"
        )
        flags = 0 if self.headless else pygame.RESIZABLE
        self.screen = pygame.display.set_mode((self.width, self.height), flags)
        self.clock = pygame.time.Clock()

        self.font_title = pygame.font.SysFont("Segoe UI, Arial", 17, bold=True)
        self.font_header = pygame.font.SysFont("Segoe UI, Arial", 14, bold=True)
        self.font_body = pygame.font.SysFont("Segoe UI, Arial", 12)
        self.font_small = pygame.font.SysFont("Segoe UI, Arial", 11)
        self.font_mono = pygame.font.SysFont("Consolas, Courier New", 11)
        self.font_metric = pygame.font.SysFont("Segoe UI, Arial", 16, bold=True)

        self.buttons: Dict[str, pygame.Rect] = {}
        self.is_running = True
        self._is_dragging_map = False
        self._drag_last_pos: Tuple[int, int] = (0, 0)
        self._drag_delta_accum: Tuple[int, int] = (0, 0)

        self._compute_layout()
        self.map_renderer = GISMapRenderer(self.simulation, self.map_rect)

    def _compute_layout(self) -> None:
        pad = 8
        top_h = 54
        bottom_h = 132
        right_w = max(360, min(420, int(self.width * 0.29)))

        self.top_rect = pygame.Rect(pad, pad, self.width - 2 * pad, top_h)
        mid_top = self.top_rect.bottom + pad
        mid_h = max(320, self.height - mid_top - bottom_h - 2 * pad)

        self.map_rect = pygame.Rect(
            pad,
            mid_top,
            max(460, self.width - right_w - 3 * pad),
            mid_h,
        )
        self.side_rect = pygame.Rect(
            self.map_rect.right + pad,
            mid_top,
            right_w,
            mid_h,
        )
        self.bottom_rect = pygame.Rect(
            pad,
            mid_top + mid_h + pad,
            self.width - 2 * pad,
            bottom_h,
        )

    def toggle_fullscreen(self) -> None:
        if self.headless:
            return
        self.is_fullscreen = not self.is_fullscreen
        if self.is_fullscreen:
            self._windowed_size = (self.width, self.height)
            self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
            self.width, self.height = self.screen.get_size()
        else:
            self.width, self.height = self._windowed_size
            self.screen = pygame.display.set_mode((self.width, self.height), pygame.RESIZABLE)
        self._compute_layout()
        self.map_renderer.set_viewport(self.map_rect)
        self.map_renderer.fit_corridor_view()

    def handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.is_running = False
            elif event.type == pygame.VIDEORESIZE and not self.is_fullscreen:
                self.width = max(1020, event.w)
                self.height = max(640, event.h)
                self.screen = pygame.display.set_mode((self.width, self.height), pygame.RESIZABLE)
                self._compute_layout()
                self.map_renderer.set_viewport(self.map_rect)
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if self.is_fullscreen:
                        self.toggle_fullscreen()
                    else:
                        self.is_running = False
                elif event.key == pygame.K_q:
                    self.is_running = False
                elif event.key == pygame.K_F11:
                    self.toggle_fullscreen()
                elif event.key == pygame.K_SPACE:
                    self.simulation.is_paused = not self.simulation.is_paused
                elif event.key == pygame.K_r:
                    self.simulation.reset()
                    self.map_renderer.invalidate_cache()
                elif event.key == pygame.K_v:
                    self.map_renderer.fit_corridor_view()
                elif event.key == pygame.K_l:
                    self.map_renderer.show_all_routes = not self.map_renderer.show_all_routes
                elif event.key == pygame.K_n:
                    step_s = 2.0 if self.simulation.bundle.network_type == "custom" else 15.0
                    self.simulation.step_sim(step_s)
                elif event.key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
                    self.map_renderer.camera.zoom_at(self.map_rect.center, 1.25)
                elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                    self.map_renderer.camera.zoom_at(self.map_rect.center, 0.8)
                elif event.key == pygame.K_1:
                    self.simulation.speed_multiplier = 0.5
                elif event.key == pygame.K_2:
                    self.simulation.speed_multiplier = 1.0
                elif event.key == pygame.K_3:
                    self.simulation.speed_multiplier = 2.0
                elif event.key in (pygame.K_4, pygame.K_5):
                    self.simulation.speed_multiplier = 5.0
            elif event.type == pygame.MOUSEWHEEL:
                pos = pygame.mouse.get_pos()
                if self.map_rect.collidepoint(pos):
                    factor = 1.18 if event.y > 0 else (1.0 / 1.18)
                    self.map_renderer.camera.zoom_at(pos, factor)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    if self._handle_button_click(event.pos):
                        pass
                    elif self.map_rect.collidepoint(event.pos):
                        self._is_dragging_map = True
                        self._drag_last_pos = event.pos
                        self._drag_delta_accum = (0, 0)
                elif event.button == 4 and self.map_rect.collidepoint(event.pos):
                    self.map_renderer.camera.zoom_at(event.pos, 1.18)
                elif event.button == 5 and self.map_rect.collidepoint(event.pos):
                    self.map_renderer.camera.zoom_at(event.pos, 1.0 / 1.18)
            elif event.type == pygame.MOUSEMOTION and self._is_dragging_map:
                dx = event.pos[0] - self._drag_last_pos[0]
                dy = event.pos[1] - self._drag_last_pos[1]
                self._drag_last_pos = event.pos
                self._drag_delta_accum = (self._drag_delta_accum[0] + dx, self._drag_delta_accum[1] + dy)
                self.map_renderer.camera.pan_by_pixels(dx, dy)
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if self._is_dragging_map:
                    self._is_dragging_map = False
                    self._drag_delta_accum = (0, 0)
                    self.map_renderer.invalidate_cache()

    def _handle_button_click(self, pos: Tuple[int, int]) -> bool:
        for name, rect in self.buttons.items():
            if not rect.collidepoint(pos):
                continue
            if name == "play_pause":
                self.simulation.is_paused = not self.simulation.is_paused
            elif name == "step":
                step_s = 2.0 if self.simulation.bundle.network_type == "custom" else 15.0
                self.simulation.step_sim(step_s)
            elif name == "reset":
                self.simulation.reset()
                self.map_renderer.invalidate_cache()
            elif name == "spd_05":
                self.simulation.speed_multiplier = 0.5
            elif name == "spd_1":
                self.simulation.speed_multiplier = 1.0
            elif name == "spd_2":
                self.simulation.speed_multiplier = 2.0
            elif name == "spd_5":
                self.simulation.speed_multiplier = 5.0
            elif name == "zoom_in":
                self.map_renderer.camera.zoom_at(self.map_rect.center, 1.25)
            elif name == "zoom_out":
                self.map_renderer.camera.zoom_at(self.map_rect.center, 0.8)
            elif name == "fit_view":
                self.map_renderer.fit_corridor_view()
            elif name == "routes":
                self.map_renderer.show_all_routes = not self.map_renderer.show_all_routes
            elif name == "fullscreen":
                self.toggle_fullscreen()
            return True
        return False

    def _draw_btn(self, key: str, rect: pygame.Rect, label: str, active: bool = False) -> None:
        self.buttons[key] = rect
        bg = self.BTN_ACTIVE if active else self.BTN_BG
        pygame.draw.rect(self.screen, bg, rect, border_radius=5)
        pygame.draw.rect(self.screen, self.BORDER, rect, width=1, border_radius=5)
        txt = self.font_small.render(label, True, self.TEXT_MAIN)
        self.screen.blit(txt, txt.get_rect(center=rect.center))

    @staticmethod
    def _wrap_text(font: pygame.font.Font, text: str, max_width: int, max_lines: int = 3) -> List[str]:
        words = text.split()
        lines: List[str] = []
        curr = ""
        for word in words:
            trial = f"{curr} {word}".strip()
            if font.size(trial)[0] <= max_width:
                curr = trial
            else:
                if curr:
                    lines.append(curr)
                curr = word
                if len(lines) >= max_lines:
                    break
        if curr and len(lines) < max_lines:
            lines.append(curr)
        return lines

    def _draw_top_bar(self) -> None:
        r = self.top_rect
        pygame.draw.rect(self.screen, self.PANEL_BG, r, border_radius=7)
        pygame.draw.rect(self.screen, self.BORDER, r, width=1, border_radius=7)

        bundle = self.simulation.bundle
        title_s = self.font_title.render(f"GeoPulse GIS  |  {bundle.title[:48]}", True, self.TEXT_MAIN)
        self.screen.blit(title_s, (r.x + 12, r.y + 6))

        n_frames = len(self.simulation.engine.frames)
        f_idx = self.simulation.active_frame_index + 1
        upd_txt = "TRAFFIC UPDATE ACTIVE" if self.simulation.update_became_valid else "INITIAL FORECAST"
        upd_col = self.ACCENT_RED if self.simulation.update_became_valid else self.ACCENT_GREEN
        if self.simulation.all_finished:
            upd_txt = "JOURNEYS COMPLETE"
            upd_col = self.ACCENT_CYAN

        meta_s = self.font_small.render(
            f"Sim +{self.simulation.sim_elapsed_s:.1f}s ({self.simulation.sim_time.strftime('%H:%M:%S')} UTC)  |  "
            f"Frame {f_idx}/{n_frames}  |  ",
            True,
            self.TEXT_MUTED,
        )
        self.screen.blit(meta_s, (r.x + 12, r.y + 30))
        self.screen.blit(self.font_small.render(upd_txt, True, upd_col), (r.x + 12 + meta_s.get_width(), r.y + 30))

        self.buttons.clear()
        bx = r.right - 10
        by = r.y + 12
        specs = [
            ("fullscreen", "Win" if self.is_fullscreen else "Full", self.is_fullscreen, 40),
            ("routes", "All" if self.map_renderer.show_all_routes else "Geo", self.map_renderer.show_all_routes, 36),
            ("fit_view", "Fit (V)", False, 48),
            ("zoom_in", "+", False, 26),
            ("zoom_out", "-", False, 26),
            ("spd_5", "5x", self.simulation.speed_multiplier == 5.0, 32),
            ("spd_2", "2x", self.simulation.speed_multiplier == 2.0, 32),
            ("spd_1", "1x", self.simulation.speed_multiplier == 1.0, 32),
            ("spd_05", "0.5x", self.simulation.speed_multiplier == 0.5, 38),
            ("reset", "Reset", False, 48),
            ("step", "Step", False, 44),
            ("play_pause", "Play" if self.simulation.is_paused else "Pause", not self.simulation.is_paused, 52),
        ]
        for key, lbl, active, bw in specs:
            bx -= bw
            self._draw_btn(key, pygame.Rect(bx, by, bw, 28), lbl, active)
            bx -= 4

    def _draw_side_panel(self) -> None:
        r = self.side_rect
        pygame.draw.rect(self.screen, self.PANEL_BG, r, border_radius=7)
        pygame.draw.rect(self.screen, self.BORDER, r, width=1, border_radius=7)

        x = r.x + 10
        w = r.width - 20
        y = r.y + 10
        geo: StrategyAgentState = self.simulation.agents["geopulse_two_edge"]

        # ------------------------------------------------------------------
        # 1. GeoPulse Decision Panel (full node IDs, never truncated)
        # ------------------------------------------------------------------
        self.screen.blit(
            self.font_header.render("GEOPULSE TWO-EDGE DECISION PANEL", True, self.ACCENT_GREEN),
            (x, y),
        )
        y += 22

        info_box = pygame.Rect(x, y, w, 54)
        pygame.draw.rect(self.screen, self.CARD_BG, info_box, border_radius=6)
        pygame.draw.rect(self.screen, self.BORDER, info_box, width=1, border_radius=6)
        self.screen.blit(self.font_mono.render(f"Current Node : {geo.current_node}", True, self.TEXT_MAIN), (x + 8, y + 6))
        self.screen.blit(self.font_mono.render(f"Next Junction: {geo.next_junction}", True, self.ACCENT_CYAN), (x + 8, y + 23))
        self.screen.blit(
            self.font_small.render(
                f"Decisions: {geo.intersection_decisions}  |  Alt Selected: {geo.two_edge_alternative_selections}  |  Fallbacks: {geo.dijkstra_fallback_steps}",
                True,
                self.TEXT_MUTED,
            ),
            (x + 8, y + 38),
        )
        y += 60

        # Candidate A & Candidate B detailed cards (stacked full-width so long OSM IDs fit cleanly!)
        def _draw_cand_card(
            title: str,
            edge,
            pred_s: Optional[float],
            tail_s: Optional[float],
            score_s: Optional[float],
            is_selected: bool,
            accent: Tuple[int, int, int],
        ) -> None:
            nonlocal y
            card = pygame.Rect(x, y, w, 66)
            pygame.draw.rect(self.screen, self.CARD_BG, card, border_radius=6)
            pygame.draw.rect(
                self.screen,
                self.ACCENT_GREEN if is_selected else accent,
                card,
                width=2 if is_selected else 1,
                border_radius=6,
            )
            badge = " [SELECTED]" if is_selected else ""
            self.screen.blit(
                self.font_body.render(f"{title}{badge}", True, self.ACCENT_GREEN if is_selected else accent),
                (x + 8, y + 5),
            )
            if edge is not None:
                edge_str = f"Edge: {edge[0]} -> {edge[1]}"
                p_txt = f"{pred_s:.2f}s" if pred_s is not None else "--"
                t_txt = f"{tail_s:.2f}s" if tail_s is not None else "--"
                c_txt = f"{score_s:.2f}s" if score_s is not None else "--"
                self.screen.blit(self.font_mono.render(edge_str, True, self.TEXT_MAIN), (x + 8, y + 23))
                self.screen.blit(
                    self.font_mono.render(f"Pred: {p_txt}  |  Dijkstra Tail: {t_txt}", True, self.TEXT_MUTED),
                    (x + 8, y + 37),
                )
                self.screen.blit(
                    self.font_mono.render(f"Combined Score: {c_txt}", True, accent),
                    (x + 8, y + 50),
                )
            else:
                self.screen.blit(self.font_small.render("None (Forced single reachable corridor)", True, self.TEXT_MUTED), (x + 8, y + 28))
            y += 72

        _draw_cand_card(
            "Candidate A (Planned Edge)",
            geo.candidate_a,
            geo.pred_time_a,
            geo.tail_cost_a,
            geo.score_a,
            is_selected=(geo.candidate_a is not None and geo.selected_candidate_slot == "A"),
            accent=self.ACCENT_CYAN,
        )
        _draw_cand_card(
            "Candidate B (Alternative Edge)",
            geo.candidate_b,
            geo.pred_time_b,
            geo.tail_cost_b,
            geo.score_b,
            is_selected=(geo.candidate_b is not None and geo.selected_candidate_slot == "B"),
            accent=self.ACCENT_PINK,
        )

        # Explanation box
        exp_h = 56
        exp_box = pygame.Rect(x, y, w, exp_h)
        pygame.draw.rect(self.screen, (18, 26, 43), exp_box, border_radius=6)
        pygame.draw.rect(self.screen, self.BORDER, exp_box, width=1, border_radius=6)
        self.screen.blit(self.font_small.render("Decision Explanation:", True, self.ACCENT_GREEN), (x + 8, y + 4))
        for idx, line in enumerate(self._wrap_text(self.font_small, geo.decision_reason, w - 16, max_lines=3)):
            self.screen.blit(self.font_small.render(line, True, self.TEXT_MAIN), (x + 8, y + 18 + idx * 12))
        y += exp_h + 8

        # ------------------------------------------------------------------
        # 2. Traffic Timeline Panel
        # ------------------------------------------------------------------
        tl_h = max(110, r.bottom - y - 8)
        tl_box = pygame.Rect(x, y, w, tl_h)
        pygame.draw.rect(self.screen, self.CARD_BG, tl_box, border_radius=6)
        pygame.draw.rect(self.screen, self.BORDER, tl_box, width=1, border_radius=6)

        ty = y + 7
        self.screen.blit(self.font_header.render("TRAFFIC REPLAY & UPDATE TIMELINE", True, self.TEXT_MAIN), (x + 8, ty))
        ty += 20

        frames = self.simulation.engine.frames
        cur_idx = self.simulation.active_frame_index
        cur_frame = frames[cur_idx]
        self.screen.blit(
            self.font_small.render(
                f"Active Frame {cur_idx + 1}/{len(frames)}  |  Valid: {cur_frame.target_valid_timestamp.strftime('%H:%M UTC')}",
                True,
                self.ACCENT_CYAN,
            ),
            (x + 8, ty),
        )
        ty += 15

        # Show sliding window of up to 8 hourly frames on timeline bar
        win_start = max(0, min(cur_idx - 2, len(frames) - 8))
        win_frames = frames[win_start : win_start + 8]
        bar_x = x + 12
        bar_w = w - 24
        bar_y = ty + 10
        pygame.draw.line(self.screen, (71, 85, 105), (bar_x, bar_y), (bar_x + bar_w, bar_y), width=3)

        step_x = bar_w / max(1, len(win_frames) - 1) if len(win_frames) > 1 else bar_w
        for idx, frame in enumerate(win_frames):
            abs_idx = win_start + idx
            px = int(bar_x + (idx * step_x if len(win_frames) > 1 else bar_w * 0.5))
            is_active = abs_idx == cur_idx
            is_init = abs_idx == self.simulation.initial_frame_index
            dot_col = self.ACCENT_RED if (is_active and abs_idx > self.simulation.initial_frame_index) else (
                self.ACCENT_GREEN if is_active else (self.ACCENT_BLUE if is_init else (100, 116, 139))
            )
            pygame.draw.circle(self.screen, dot_col, (px, bar_y), 6 if is_active else 4)
            lbl = frame.target_valid_timestamp.strftime("%H:%M")
            ls = self.font_small.render(lbl, True, self.TEXT_MAIN if is_active else self.TEXT_MUTED)
            self.screen.blit(ls, (px - ls.get_width() // 2, bar_y + 8))

        ty = bar_y + 26
        dyn = self.simulation.agents["dynamic_dijkstra"]
        dyn_app = f"at node {dyn.last_update_applied_node} ({dyn.last_update_applied_time})" if dyn.last_update_applied_node else "pending next update"
        geo_app = f"at node {geo.last_update_applied_node} ({geo.last_update_applied_time})" if geo.last_update_applied_node else "pending next update"
        if ty + 28 < tl_box.bottom:
            self.screen.blit(self.font_small.render(f"Obs Stream: {'Realized + Forecast' if cur_frame.has_realized_observations else 'Static'}", True, self.TEXT_MUTED), (x + 8, ty))
            self.screen.blit(self.font_small.render(f"Dynamic applied: {dyn_app}"[:48], True, self.ACCENT_AMBER), (x + 8, ty + 14))
            if ty + 40 < tl_box.bottom:
                self.screen.blit(self.font_small.render(f"GeoPulse applied: {geo_app}"[:48], True, self.ACCENT_GREEN), (x + 8, ty + 28))

    def _draw_bottom_panel(self) -> None:
        r = self.bottom_rect
        pygame.draw.rect(self.screen, self.PANEL_BG, r, border_radius=7)
        pygame.draw.rect(
            self.screen,
            self.ACCENT_GREEN if self.simulation.all_finished else self.BORDER,
            r,
            width=2 if self.simulation.all_finished else 1,
            border_radius=7,
        )

        pad = 8
        banner_h = 24
        card_w = (r.width - 4 * pad) // 3
        card_h = r.height - banner_h - 2 * pad

        static_a = self.simulation.agents["static_dijkstra"]
        dynamic_a = self.simulation.agents["dynamic_dijkstra"]
        geo_a = self.simulation.agents["geopulse_two_edge"]

        cards = [
            (
                "Static Dijkstra",
                self.ACCENT_BLUE,
                static_a,
                [
                    f"Elapsed: {self.simulation.live_elapsed_s('static_dijkstra'):.2f} s   |   Dist: {self.simulation.live_distance_m('static_dijkstra'):.1f} m",
                    f"Route Edges: {len(static_a.traversed_edges)}   |   Status: {static_a.status_label[:20]}",
                ],
            ),
            (
                "Dynamic Dijkstra",
                self.ACCENT_AMBER,
                dynamic_a,
                [
                    f"Elapsed: {self.simulation.live_elapsed_s('dynamic_dijkstra'):.2f} s   |   Dist: {self.simulation.live_distance_m('dynamic_dijkstra'):.1f} m",
                    f"Updates: {dynamic_a.prediction_updates_applied}   |   Reroutes: {dynamic_a.dijkstra_reroutes}   |   {dynamic_a.status_label[:16]}",
                ],
            ),
            (
                "GeoPulse Two-Edge",
                self.ACCENT_GREEN,
                geo_a,
                [
                    f"Elapsed: {self.simulation.live_elapsed_s('geopulse_two_edge'):.2f} s   |   Dist: {self.simulation.live_distance_m('geopulse_two_edge'):.1f} m",
                    f"Decisions: {geo_a.intersection_decisions}  |  Alt: {geo_a.two_edge_alternative_selections}  |  Fallbacks: {geo_a.dijkstra_fallback_steps}",
                ],
            ),
        ]

        for idx, (title, accent, agent, lines) in enumerate(cards):
            cx = r.x + pad + idx * (card_w + pad)
            cy = r.y + pad
            card = pygame.Rect(cx, cy, card_w, card_h)
            pygame.draw.rect(self.screen, self.CARD_BG, card, border_radius=6)
            pygame.draw.rect(
                self.screen,
                self.ACCENT_GREEN if agent.arrived else accent,
                card,
                width=2 if agent.arrived else 1,
                border_radius=6,
            )
            self.screen.blit(self.font_header.render(title, True, accent), (cx + 10, cy + 7))
            st_col = self.ACCENT_GREEN if agent.arrived else self.TEXT_MUTED
            st_surf = self.font_small.render("ARRIVED" if agent.arrived else "RUNNING", True, st_col)
            self.screen.blit(st_surf, (card.right - st_surf.get_width() - 10, cy + 9))

            for l_idx, line in enumerate(lines):
                self.screen.blit(self.font_mono.render(line, True, self.TEXT_MAIN), (cx + 10, cy + 31 + l_idx * 20))

        # Bottom banner: show final winner ONLY after all journeys complete
        by = r.bottom - banner_h
        if self.simulation.all_finished:
            rows = self.simulation.get_comparison_rows()
            completed = [row for row in rows if row["arrived"] and not row["failed"]]
            if completed:
                best_t = min(row["elapsed_time_s"] for row in completed)
                winners = " & ".join(
                    row["label"] for row in completed if abs(row["elapsed_time_s"] - best_t) <= 1e-6
                )
                static_row = next(row for row in rows if row["strategy"] == "static_dijkstra")
                if static_row["arrived"] and static_row["elapsed_time_s"] > best_t + 1e-6:
                    gain_s = static_row["elapsed_time_s"] - best_t
                    gain_pct = (gain_s / static_row["elapsed_time_s"]) * 100.0
                    msg = f"FINAL WINNER: {winners} ({best_t:.2f}s) — Saved {gain_s:.2f}s ({gain_pct:.1f}%) vs Static Dijkstra"
                else:
                    msg = f"FINAL WINNER: {winners} ({best_t:.2f}s)"
                self.screen.blit(self.font_body.render(msg, True, self.ACCENT_GOLD), (r.x + 12, by + 2))
        else:
            hint = "Mouse Wheel: Zoom  |  Left-Drag: Pan  |  V: Fit View  |  Space: Pause  |  F11: Fullscreen"
            self.screen.blit(self.font_small.render(hint, True, self.TEXT_MUTED), (r.x + 12, by + 4))

    def render_frame(self) -> None:
        self.screen.fill(self.BG_COLOR)
        self._draw_top_bar()
        drag_preview = self._drag_delta_accum if self._is_dragging_map else (0, 0)
        self.map_renderer.draw(self.screen, drag_preview=drag_preview)
        self._draw_side_panel()
        self._draw_bottom_panel()
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
