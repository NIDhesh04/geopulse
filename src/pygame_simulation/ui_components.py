"""
GeoPulse Pygame UI & HUD Components

Renders the side dashboard panel, candidate comparison cards, telemetry metrics,
and interactive simulation controls.
"""

from typing import Dict, List, Tuple, Optional, Any
import os
# Ensure headless environments can import os
# Ensure headless environments can import pygame without a real display
if os.getenv('SDL_VIDEODRIVER') is None:
    os.environ['SDL_VIDEODRIVER'] = 'dummy'

try:
    import pygame
except ImportError:
    # Minimal pygame stub for headless test environments
    class _SurfaceStub:
        def __init__(self, *args, **kwargs):
            pass
        def fill(self, *args, **kwargs):
            pass
        def blit(self, *args, **kwargs):
            pass
        def get_rect(self, *args, **kwargs):
            return self
        def inflate(self, *args, **kwargs):
            return self
    class _FontStub:
        def __init__(self, *args, **kwargs):
            pass
        def render(self, *args, **kwargs):
            return _SurfaceStub()
        def get_width(self):
            return 0
        def get_height(self):
            return 0
        def get_rect(self, *args, **kwargs):
            return _SurfaceStub()
    class _PygameStub:
        Rect = lambda *args, **kwargs: (0,0,0,0)
        Surface = _SurfaceStub
        font = types.SimpleNamespace(SysFont=lambda *a, **kw: _FontStub())
        def init(self):
            pass
        def quit(self):
            pass
        def draw(self, *args, **kwargs):
            pass
    pygame = _PygameStub()
if os.getenv('SDL_VIDEODRIVER') is None:
    os.environ['SDL_VIDEODRIVER'] = 'dummy'

import os
# Ensure headless environments can import pygame without a real display
if os.getenv('SDL_VIDEODRIVER') is None:
    os.environ['SDL_VIDEODRIVER'] = 'dummy'

try:
    import pygame
except ImportError:
    # Minimal pygame stub for headless test environments
    class _SurfaceStub:
        def __init__(self, *args, **kwargs):
            pass
        def fill(self, *args, **kwargs):
            pass
        def blit(self, *args, **kwargs):
            pass
        def get_rect(self, *args, **kwargs):
            return self
        def inflate(self, *args, **kwargs):
            return self
    class _FontStub:
        def __init__(self, *args, **kwargs):
            pass
        def render(self, *args, **kwargs):
            return _SurfaceStub()
        def get_width(self):
            return 0
        def get_height(self):
            return 0
        def get_rect(self, *args, **kwargs):
            return _SurfaceStub()
    class _PygameStub:
        Rect = lambda *args, **kwargs: (0,0,0,0)
        Surface = _SurfaceStub
        font = types.SimpleNamespace(SysFont=lambda *a, **kw: _FontStub())
        def init(self):
            pass
        def quit(self):
            pass
        def draw(self, *args, **kwargs):
            pass
    pygame = _PygameStub()


class HUDPanel:
    """Manages the UI side panel displaying real-time algorithm state and controls."""

    # Colors
    PANEL_BG = (15, 23, 42)          # Slate 900
    PANEL_BORDER = (51, 65, 85)      # Slate 700
    CARD_BG = (30, 41, 59)           # Slate 800
    TEXT_MAIN = (248, 250, 252)      # Slate 50
    TEXT_MUTED = (148, 163, 184)     # Slate 400
    ACCENT_CYAN = (6, 182, 212)
    ACCENT_ORANGE = (249, 115, 22)
    ACCENT_GREEN = (16, 185, 129)
    ACCENT_YELLOW = (234, 179, 8)
    BTN_BG = (51, 65, 85)
    BTN_ACTIVE = (37, 99, 235)

    def __init__(self, rect: pygame.Rect):
        self.rect = rect
        pygame.font.init()
        self.font_title = pygame.font.SysFont('Segoe UI, Arial', 18, bold=True)
        self.font_header = pygame.font.SysFont('Segoe UI, Arial', 14, bold=True)
        self.font_body = pygame.font.SysFont('Segoe UI, Arial', 12)
        self.font_mono = pygame.font.SysFont('Consolas, Courier', 11)

        # Buttons rects for mouse hit detection
        self.buttons: Dict[str, pygame.Rect] = {}

    def draw(
        self,
        surface: pygame.Surface,
        state_dict: Dict[str, Any]
    ):
        """Draws the complete HUD dashboard."""
        # 1. Panel background & border
        pygame.draw.rect(surface, self.PANEL_BG, self.rect)
        pygame.draw.line(surface, self.PANEL_BORDER, self.rect.topleft, self.rect.bottomleft, width=2)

        x = self.rect.x + 14
        y = self.rect.y + 12
        w = self.rect.width - 28

        # Header Title
        title_surf = self.font_title.render("GeoPulse — Sequential Routing", True, self.TEXT_MAIN)
        surface.blit(title_surf, (x, y))
        y += 24

        subtitle = self.font_body.render("Two-Edge Decision & Dynamic Rerouting", True, self.TEXT_MUTED)
        surface.blit(subtitle, (x, y))
        y += 26

        # -------------------------------------------------------------
        # Section 1: Journey Status & Algorithmic Telemetry
        # -------------------------------------------------------------
        card_h = 108
        pygame.draw.rect(surface, self.CARD_BG, (x, y, w, card_h), border_radius=6)
        pygame.draw.rect(surface, self.PANEL_BORDER, (x, y, w, card_h), width=1, border_radius=6)

        cy = y + 8
        self._draw_label_value(surface, x + 8, cy, "Algorithm:", state_dict.get('strategy_name', 'Greedy'), self.ACCENT_CYAN)
        cy += 18
        self._draw_label_value(surface, x + 8, cy, "Origin -> Dest:", f"{state_dict.get('origin', '')} -> {state_dict.get('destination', '')}", self.TEXT_MAIN)
        cy += 18
        self._draw_label_value(surface, x + 8, cy, "Current Node:", str(state_dict.get('current_node', '')), self.ACCENT_YELLOW)
        cy += 18
        self._draw_label_value(surface, x + 8, cy, "Elapsed Journey:", f"{state_dict.get('elapsed_time_s', 0.0):.1f}s | {state_dict.get('distance_m', 0.0):.0f}m", self.TEXT_MAIN)
        cy += 18
        self._draw_label_value(surface, x + 8, cy, "Decisions / Reroutes:", f"{state_dict.get('decisions_count', 0)} hops | {state_dict.get('reroutes_count', 0)} reroutes", self.ACCENT_GREEN)

        y += card_h + 12

        # -------------------------------------------------------------
        # Section 2: Candidate A vs Candidate B Comparison Card
        # -------------------------------------------------------------
        card_cand_h = 190
        pygame.draw.rect(surface, self.CARD_BG, (x, y, w, card_cand_h), border_radius=6)
        pygame.draw.rect(surface, self.PANEL_BORDER, (x, y, w, card_cand_h), width=1, border_radius=6)

        cand_title = self.font_header.render("TWO-EDGE CANDIDATE EVALUATION", True, self.TEXT_MAIN)
        surface.blit(cand_title, (x + 8, y + 8))

        # Candidate A Box
        box_w = (w - 24) // 2
        box_a = pygame.Rect(x + 8, y + 28, box_w, 98)
        is_a_chosen = state_dict.get('chosen_candidate') == 'A'
        border_a = self.ACCENT_GREEN if is_a_chosen else self.ACCENT_CYAN
        pygame.draw.rect(surface, (20, 30, 45), box_a, border_radius=4)
        pygame.draw.rect(surface, border_a, box_a, width=2 if is_a_chosen else 1, border_radius=4)

        surface.blit(self.font_header.render("Candidate A", True, self.ACCENT_CYAN), (box_a.x + 6, box_a.y + 4))
        cand_a_data = state_dict.get('candidate_a')
        if cand_a_data:
            self._draw_text(surface, box_a.x + 6, box_a.y + 22, f"Edge: {cand_a_data.get('edge', '')}", self.TEXT_MAIN)
            self._draw_text(surface, box_a.x + 6, box_a.y + 38, f"Speed: {cand_a_data.get('speed', 0.0):.1f} km/h", self.TEXT_MUTED)
            self._draw_text(surface, box_a.x + 6, box_a.y + 54, f"Cost: {cand_a_data.get('cost', 0.0):.1f}s", self.TEXT_MUTED)
            self._draw_text(surface, box_a.x + 6, box_a.y + 70, f"Score: {cand_a_data.get('score', 0.0):.1f}", self.ACCENT_CYAN)
        else:
            self._draw_text(surface, box_a.x + 6, box_a.y + 35, "None", self.TEXT_MUTED)

        # Candidate B Box
        box_b = pygame.Rect(x + 16 + box_w, y + 28, box_w, 98)
        is_b_chosen = state_dict.get('chosen_candidate') == 'B'
        border_b = self.ACCENT_GREEN if is_b_chosen else self.ACCENT_ORANGE
        pygame.draw.rect(surface, (20, 30, 45), box_b, border_radius=4)
        pygame.draw.rect(surface, border_b, box_b, width=2 if is_b_chosen else 1, border_radius=4)

        surface.blit(self.font_header.render("Candidate B", True, self.ACCENT_ORANGE), (box_b.x + 6, box_b.y + 4))
        cand_b_data = state_dict.get('candidate_b')
        if cand_b_data:
            self._draw_text(surface, box_b.x + 6, box_b.y + 22, f"Edge: {cand_b_data.get('edge', '')}", self.TEXT_MAIN)
            self._draw_text(surface, box_b.x + 6, box_b.y + 38, f"Speed: {cand_b_data.get('speed', 0.0):.1f} km/h", self.TEXT_MUTED)
            self._draw_text(surface, box_b.x + 6, box_b.y + 54, f"Cost: {cand_b_data.get('cost', 0.0):.1f}s", self.TEXT_MUTED)
            self._draw_text(surface, box_b.x + 6, box_b.y + 70, f"Score: {cand_b_data.get('score', 0.0):.1f}", self.ACCENT_ORANGE)
        else:
            self._draw_text(surface, box_b.x + 6, box_b.y + 35, "(Forced Cont.)", self.TEXT_MUTED)

        # Decision Reason Banner
        reason = state_dict.get('decision_reason', '')
        reason_y = y + 132
        pygame.draw.rect(surface, (15, 23, 42), (x + 8, reason_y, w - 16, 50), border_radius=4)
        pygame.draw.rect(surface, self.PANEL_BORDER, (x + 8, reason_y, w - 16, 50), width=1, border_radius=4)

        self._draw_text(surface, x + 14, reason_y + 4, "Decision Directive:", self.ACCENT_GREEN)
        # Word wrap reason in 2 lines
        if len(reason) > 42:
            self._draw_text(surface, x + 14, reason_y + 18, reason[:42], self.TEXT_MAIN)
            self._draw_text(surface, x + 14, reason_y + 32, reason[42:84], self.TEXT_MAIN)
        else:
            self._draw_text(surface, x + 14, reason_y + 22, reason, self.TEXT_MAIN)

        y += card_cand_h + 12

        # -------------------------------------------------------------
        # Section 3: Interactive Simulation Controls
        # -------------------------------------------------------------
        ctrl_h = 175
        pygame.draw.rect(surface, self.CARD_BG, (x, y, w, ctrl_h), border_radius=6)
        pygame.draw.rect(surface, self.PANEL_BORDER, (x, y, w, ctrl_h), width=1, border_radius=6)

        surface.blit(self.font_header.render("SIMULATION CONTROLS", True, self.TEXT_MAIN), (x + 8, y + 8))

        btn_y = y + 30
        btn_w = (w - 24) // 3
        # Row 1: Play/Pause, Step, Reset
        is_paused = state_dict.get('is_paused', False)
        self.buttons['play_pause'] = pygame.Rect(x + 8, btn_y, btn_w, 28)
        self.buttons['step'] = pygame.Rect(x + 16 + btn_w, btn_y, btn_w, 28)
        self.buttons['reset'] = pygame.Rect(x + 24 + 2 * btn_w, btn_y, btn_w, 28)

        self._draw_button(surface, self.buttons['play_pause'], "Resume" if is_paused else "Pause", is_active=not is_paused)
        self._draw_button(surface, self.buttons['step'], "Step (N)", is_active=False)
        self._draw_button(surface, self.buttons['reset'], "Reset (R)", is_active=False)

        # Row 2: Speed buttons (1x, 2x, 5x)
        btn_y += 36
        curr_speed = state_dict.get('speed_multiplier', 1)
        self.buttons['speed_1x'] = pygame.Rect(x + 8, btn_y, btn_w, 26)
        self.buttons['speed_2x'] = pygame.Rect(x + 16 + btn_w, btn_y, btn_w, 26)
        self.buttons['speed_5x'] = pygame.Rect(x + 24 + 2 * btn_w, btn_y, btn_w, 26)

        self._draw_button(surface, self.buttons['speed_1x'], "1x Speed", is_active=(curr_speed == 1))
        self._draw_button(surface, self.buttons['speed_2x'], "2x Speed", is_active=(curr_speed == 2))
        self._draw_button(surface, self.buttons['speed_5x'], "5x Speed", is_active=(curr_speed == 5))

        # Row 3: Strategy Cycle Button
        btn_y += 34
        self.buttons['cycle_strategy'] = pygame.Rect(x + 8, btn_y, w - 16, 28)
        self._draw_button(surface, self.buttons['cycle_strategy'], f"Mode: {state_dict.get('strategy_name', '')[:26]}", is_active=True)

        # Row 4: Scenario Toggle Button
        btn_y += 34
        self.buttons['toggle_network'] = pygame.Rect(x + 8, btn_y, w - 16, 28)
        net_name = "Custom Grid" if state_dict.get('network_type') == 'custom' else "Bhubaneswar OSM"
        self._draw_button(surface, self.buttons['toggle_network'], f"Network: {net_name}", is_active=False)

    def _draw_label_value(self, surface: pygame.Surface, x: int, y: int, label: str, value: str, val_col: Tuple[int, int, int]):
        l_surf = self.font_body.render(label, True, self.TEXT_MUTED)
        v_surf = self.font_body.render(value, True, val_col)
        surface.blit(l_surf, (x, y))
        surface.blit(v_surf, (x + 130, y))

    def _draw_text(self, surface: pygame.Surface, x: int, y: int, text: str, col: Tuple[int, int, int]):
        surf = self.font_mono.render(text, True, col)
        surface.blit(surf, (x, y))

    def _draw_button(self, surface: pygame.Surface, rect: pygame.Rect, text: str, is_active: bool = False):
        bg = self.BTN_ACTIVE if is_active else self.BTN_BG
        pygame.draw.rect(surface, bg, rect, border_radius=4)
        pygame.draw.rect(surface, self.PANEL_BORDER, rect, width=1, border_radius=4)
        txt_surf = self.font_body.render(text, True, self.TEXT_MAIN)
        txt_rect = txt_surf.get_rect(center=rect.center)
        surface.blit(txt_surf, txt_rect)
