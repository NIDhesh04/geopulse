"""
GeoPulse Pygame Master Renderer

Coordinates the Pygame window, background canvas, road network layer,
vehicle sprite animation, and HUD overlay dashboard.
"""

import sys
import time
import pygame
from typing import Optional

from src.pygame_simulation.road_renderer import RoadRenderer
from src.pygame_simulation.vehicle_sprite import VehicleSprite
from src.pygame_simulation.ui_components import HUDPanel
from src.pygame_simulation.simulation_controller import SimulationController, SimState


class SimulationRenderer:
    """Master rendering and event loop coordinator for GeoPulse Pygame simulation."""

    WIDTH = 1280
    HEIGHT = 720
    HUD_WIDTH = 340

    def __init__(
        self,
        controller: SimulationController,
        headless: bool = False
    ):
        self.controller = controller
        self.headless = headless

        if self.headless:
            import os
            os.environ["SDL_VIDEODRIVER"] = "dummy"

        pygame.init()
        pygame.display.set_caption("GeoPulse — Sequential Two-Edge Decision & Dynamic Rerouting Simulation")

        self.screen = pygame.display.set_mode((self.WIDTH, self.HEIGHT))
        self.clock = pygame.time.Clock()

        # Canvas layout
        self.canvas_rect = pygame.Rect(0, 0, self.WIDTH - self.HUD_WIDTH, self.HEIGHT)
        self.hud_rect = pygame.Rect(self.WIDTH - self.HUD_WIDTH, 0, self.HUD_WIDTH, self.HEIGHT)

        # Subsystems
        is_geo = (self.controller.scenario.network_type == "osm")
        self.road_renderer = RoadRenderer(
            node_coords=self.controller.scenario.node_coords,
            canvas_rect=self.canvas_rect,
            is_geographic=is_geo
        )
        self.vehicle_sprite = VehicleSprite(size=18)
        self.hud_panel = HUDPanel(self.hud_rect)

        self.is_running = True

    def handle_events(self):
        """Processes keyboard, mouse, and window quit events."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.is_running = False

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE or event.key == pygame.K_q:
                    self.is_running = False
                elif event.key == pygame.K_SPACE:
                    self.controller.is_paused = not self.controller.is_paused
                elif event.key == pygame.K_n:
                    self.controller.trigger_step()
                elif event.key == pygame.K_r:
                    self.controller.reset()
                elif event.key == pygame.K_1:
                    self.controller.speed_multiplier = 1.0
                elif event.key == pygame.K_2:
                    self.controller.speed_multiplier = 2.0
                elif event.key == pygame.K_5:
                    self.controller.speed_multiplier = 5.0

            elif event.type == pygame.MOUSEBUTTONDOWN:
                pos = event.pos
                self._handle_mouse_click(pos)

    def _handle_mouse_click(self, pos):
        """Handles clicks on HUD buttons."""
        buttons = self.hud_panel.buttons
        if 'play_pause' in buttons and buttons['play_pause'].collidepoint(pos):
            self.controller.is_paused = not self.controller.is_paused
        elif 'step' in buttons and buttons['step'].collidepoint(pos):
            self.controller.trigger_step()
        elif 'reset' in buttons and buttons['reset'].collidepoint(pos):
            self.controller.reset()
        elif 'speed_1x' in buttons and buttons['speed_1x'].collidepoint(pos):
            self.controller.speed_multiplier = 1.0
        elif 'speed_2x' in buttons and buttons['speed_2x'].collidepoint(pos):
            self.controller.speed_multiplier = 2.0
        elif 'speed_5x' in buttons and buttons['speed_5x'].collidepoint(pos):
            self.controller.speed_multiplier = 5.0
        elif 'cycle_strategy' in buttons and buttons['cycle_strategy'].collidepoint(pos):
            # Cycle through strategies
            strategies = ["greedy", "destination_aware", "lookahead_2", "lookahead_3", "adaptive"]
            cur = self.controller.strategy_type
            idx = (strategies.index(cur) + 1) % len(strategies) if cur in strategies else 0
            self.controller.set_strategy(strategies[idx])

    def render_frame(self):
        """Draws one complete frame."""
        # Clear screen with dark slate canvas
        self.screen.fill(RoadRenderer.BG_COLOR)

        # 1. Candidate edges for highlighting
        cand_a_edge = None
        cand_b_edge = None
        selected_edge = self.controller.active_edge

        if self.controller.current_decision:
            ca = self.controller.current_decision.candidate_a
            cb = self.controller.current_decision.candidate_b
            if ca:
                cand_a_edge = ca.edge_tuple
            if cb:
                cand_b_edge = cb.edge_tuple

        # 2. Draw Road Network
        self.road_renderer.draw_network(
            surface=self.screen,
            adjacency=self.controller.scenario.adjacency,
            edge_speeds=self.controller.active_speeds,
            source_node=self.controller.scenario.source_node,
            destination_node=self.controller.scenario.destination_node,
            current_node=self.controller.current_node,
            candidate_a=cand_a_edge,
            candidate_b=cand_b_edge,
            selected_edge=selected_edge,
            traversed_edges=self.controller.traversed_edges
        )

        # 3. Update & Draw Vehicle
        if self.controller.active_edge:
            p_start = self.road_renderer.project_point(self.controller.active_edge[0])
            p_end = self.road_renderer.project_point(self.controller.active_edge[1])
            if p_start and p_end:
                self.vehicle_sprite.update_motion(
                    start_px=p_start,
                    end_px=p_end,
                    progress=self.controller.active_edge_progress
                )
                self.vehicle_sprite.draw(self.screen)
        else:
            p_curr = self.road_renderer.project_point(self.controller.current_node)
            if p_curr:
                self.vehicle_sprite.current_pos = p_curr
                self.vehicle_sprite.draw(self.screen)

        # 4. Draw HUD Panel
        hud_state = self.controller.get_hud_state_dict()
        self.hud_panel.draw(self.screen, hud_state)

        pygame.display.flip()

    def run_loop(self, max_seconds: Optional[float] = None):
        """Runs the main visual rendering loop."""
        start_time = time.time()
        while self.is_running:
            dt = self.clock.tick(60) / 1000.0  # Cap at 60 FPS

            self.handle_events()
            self.controller.update(dt)
            self.render_frame()

            if max_seconds is not None and (time.time() - start_time) >= max_seconds:
                break

        pygame.quit()
