"""
GeoPulse Vehicle Sprite & Kinematic Motion Module

Simulates smooth vehicular movement along road edges with heading rotation,
kinematic pacing, and visual heading indicators.
"""

from typing import Tuple, Optional
import math
import pygame


class VehicleSprite:
    """Manages vehicle position, rotation, and rendering during transit."""

    CAR_COLOR = (59, 130, 246)       # Blue 500
    CAR_ACCENT = (255, 255, 255)     # White roof
    HEADLIGHT_COLOR = (253, 224, 71) # Light Yellow
    HALO_COLOR = (96, 165, 250, 80)  # Semi-transparent blue glow

    def __init__(self, size: int = 16):
        self.size = size
        self.current_pos: Tuple[float, float] = (0.0, 0.0)
        self.heading_rad: float = 0.0
        self.progress: float = 0.0  # 0.0 to 1.0 along active edge
        self.is_moving: bool = False

    def update_motion(
        self,
        start_px: Tuple[int, int],
        end_px: Tuple[int, int],
        progress: float
    ):
        """Updates vehicle position and heading along active edge."""
        self.progress = max(0.0, min(1.0, float(progress)))

        x1, y1 = start_px
        x2, y2 = end_px

        curr_x = x1 + self.progress * (x2 - x1)
        curr_y = y1 + self.progress * (y2 - y1)
        self.current_pos = (curr_x, curr_y)

        dx = x2 - x1
        dy = y2 - y1
        if dx != 0 or dy != 0:
            self.heading_rad = math.atan2(dy, dx)

    def draw(self, surface: pygame.Surface):
        """Draws the rotated vehicle chassis and directional marker."""
        cx, cy = int(self.current_pos[0]), int(self.current_pos[1])
        angle_deg = -math.degrees(self.heading_rad)

        # Draw glowing halo
        halo_surface = pygame.Surface((self.size * 3, self.size * 3), pygame.SRCALPHA)
        pygame.draw.circle(
            halo_surface,
            self.HALO_COLOR,
            (self.size * 1.5, self.size * 1.5),
            self.size * 1.2
        )
        surface.blit(halo_surface, (cx - self.size * 1.5, cy - self.size * 1.5))

        # Vehicle base surface (unrotated)
        w, h = self.size, int(self.size * 0.6)
        car_surf = pygame.Surface((w, h), pygame.SRCALPHA)

        # Chassis
        pygame.draw.rect(car_surf, self.CAR_COLOR, (0, 0, w, h), border_radius=3)
        # Windshield / roof
        pygame.draw.rect(car_surf, self.CAR_ACCENT, (int(w * 0.3), int(h * 0.2), int(w * 0.4), int(h * 0.6)), border_radius=1)
        # Headlights on the front edge (right side)
        pygame.draw.circle(car_surf, self.HEADLIGHT_COLOR, (w - 2, 2), 2)
        pygame.draw.circle(car_surf, self.HEADLIGHT_COLOR, (w - 2, h - 3), 2)

        # Rotate surface
        rotated_surf = pygame.transform.rotate(car_surf, angle_deg)
        new_rect = rotated_surf.get_rect(center=(cx, cy))
        surface.blit(rotated_surf, new_rect.topleft)
