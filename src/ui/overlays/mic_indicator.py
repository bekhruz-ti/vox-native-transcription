"""
Mic indicator overlay for Input-STT.

A small floating widget that shows near the cursor when recording,
providing visual feedback to the user.
"""

from typing import Optional

from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QColor, QPainter, QBrush, QPen, QCursor, QRadialGradient
from PySide6.QtCore import Qt, QTimer, Property


class MicIndicator(QWidget):
    """
    Floating microphone indicator overlay.
    
    Appears near the cursor position when recording is active.
    Features:
    - Windows 11 native-style appearance
    - Pulsing animation while recording
    - Transparent, always-on-top, click-through
    - Follows cursor position
    """
    
    # Appearance constants
    CONTENT_SIZE = 40  # Size of the mic indicator content
    SHADOW_PADDING = 8  # Extra padding for shadow
    SIZE = CONTENT_SIZE + SHADOW_PADDING * 2  # Total widget size
    CORNER_RADIUS = 8
    BACKGROUND_COLOR = QColor(45, 45, 45, 240)  # Dark with transparency
    BORDER_COLOR = QColor(70, 70, 70)
    MIC_COLOR_NORMAL = QColor(220, 53, 69)  # Red
    MIC_COLOR_DIM = QColor(160, 43, 59)     # Dimmer red
    
    # Positioning
    CURSOR_OFFSET_X = 20  # Pixels right of cursor
    CURSOR_OFFSET_Y = -25  # Pixels above cursor
    POSITION_UPDATE_INTERVAL = 100  # ms
    
    def __init__(self, parent: Optional[QWidget] = None):
        """Initialize the mic indicator."""
        super().__init__(parent)
        
        # Window flags for overlay behavior
        self.setWindowFlags(
            Qt.Tool |
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.WindowTransparentForInput  # Click-through
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        
        # Set size (includes padding for shadow)
        self.setFixedSize(self.SIZE, self.SIZE)
        
        # Animation state
        self._pulse_opacity = 1.0
        self._is_animating = False
        
        # Position update timer
        self._position_timer = QTimer(self)
        self._position_timer.timeout.connect(self._update_position)
        
        # Pulse animation timer
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._pulse_tick)
        self._pulse_direction = -1  # -1 = dimming, 1 = brightening
        
        # No QGraphicsDropShadowEffect - we paint the shadow manually
    
    def _get_pulse_opacity(self) -> float:
        """Get current pulse opacity."""
        return self._pulse_opacity
    
    def _set_pulse_opacity(self, value: float) -> None:
        """Set pulse opacity and trigger repaint."""
        self._pulse_opacity = value
        self.update()
    
    pulse_opacity = Property(float, _get_pulse_opacity, _set_pulse_opacity)
    
    def show_indicator(self) -> None:
        """Show the indicator and start animations."""
        # Position near cursor
        self._update_position()
        
        # Start position tracking
        self._position_timer.start(self.POSITION_UPDATE_INTERVAL)
        
        # Start pulse animation
        self._pulse_opacity = 1.0
        self._pulse_direction = -1
        self._pulse_timer.start(50)  # 50ms for smooth animation
        self._is_animating = True
        
        # Show
        self.show()
        self.raise_()
    
    def hide_indicator(self) -> None:
        """Hide the indicator and stop animations."""
        self._position_timer.stop()
        self._pulse_timer.stop()
        self._is_animating = False
        self.hide()
    
    def _update_position(self) -> None:
        """Update position to follow cursor."""
        cursor_pos = QCursor.pos()
        
        # Calculate new position
        new_x = cursor_pos.x() + self.CURSOR_OFFSET_X
        new_y = cursor_pos.y() + self.CURSOR_OFFSET_Y
        
        # Ensure we stay on screen
        screen = self.screen()
        if screen:
            screen_geo = screen.availableGeometry()
            
            # Clamp to screen bounds
            new_x = max(screen_geo.left(), min(new_x, screen_geo.right() - self.SIZE))
            new_y = max(screen_geo.top(), min(new_y, screen_geo.bottom() - self.SIZE))
        
        self.move(new_x, new_y)
    
    def _pulse_tick(self) -> None:
        """Update pulse animation."""
        # Animate opacity between 0.5 and 1.0
        step = 0.03 * self._pulse_direction
        self._pulse_opacity += step
        
        if self._pulse_opacity <= 0.5:
            self._pulse_opacity = 0.5
            self._pulse_direction = 1
        elif self._pulse_opacity >= 1.0:
            self._pulse_opacity = 1.0
            self._pulse_direction = -1
        
        self.update()
    
    def paintEvent(self, event) -> None:
        """Paint the indicator."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Content area (centered, with padding for shadow)
        content_x = self.SHADOW_PADDING
        content_y = self.SHADOW_PADDING - 2  # Offset up slightly for shadow below
        content_size = self.CONTENT_SIZE
        
        # Draw soft shadow (multiple semi-transparent rounded rects)
        for i in range(4, 0, -1):
            shadow_color = QColor(0, 0, 0, 15 * (5 - i))
            painter.setBrush(QBrush(shadow_color))
            painter.setPen(Qt.NoPen)
            offset = i * 1.5
            painter.drawRoundedRect(
                int(content_x - 1), int(content_y + offset),
                content_size + 2, content_size + 2,
                self.CORNER_RADIUS + 2, self.CORNER_RADIUS + 2
            )
        
        # Draw background
        painter.setBrush(QBrush(self.BACKGROUND_COLOR))
        painter.setPen(QPen(self.BORDER_COLOR, 1))
        painter.drawRoundedRect(
            content_x, content_y,
            content_size, content_size,
            self.CORNER_RADIUS, self.CORNER_RADIUS
        )
        
        # Calculate mic color with pulse
        mic_color = QColor(self.MIC_COLOR_NORMAL)
        mic_color.setAlphaF(self._pulse_opacity)
        
        # Draw microphone icon (centered in content area)
        self._draw_mic_icon(painter, mic_color, content_x, content_y, content_size)
        
        painter.end()
    
    def _draw_mic_icon(self, painter: QPainter, color: QColor, 
                       offset_x: int, offset_y: int, size: int) -> None:
        """Draw a microphone icon in the center of the content area."""
        painter.setBrush(QBrush(color))
        painter.setPen(QPen(color, 2))
        
        center_x = offset_x + size / 2
        center_y = offset_y + size / 2
        
        # Mic body (rounded rectangle)
        mic_width = size * 0.3
        mic_height = size * 0.4
        mic_x = center_x - mic_width / 2
        mic_y = center_y - mic_height / 2 - 3
        
        painter.drawRoundedRect(
            int(mic_x), int(mic_y),
            int(mic_width), int(mic_height),
            int(mic_width / 2), int(mic_width / 2)
        )
        
        # Stand (U shape)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(color, 2))
        
        stand_width = size * 0.4
        stand_x = center_x - stand_width / 2
        stand_top = mic_y + mic_height - 2
        stand_bottom = center_y + 8
        
        # Left side
        painter.drawLine(
            int(stand_x), int(stand_top),
            int(stand_x), int(stand_bottom)
        )
        
        # Right side
        painter.drawLine(
            int(stand_x + stand_width), int(stand_top),
            int(stand_x + stand_width), int(stand_bottom)
        )
        
        # Bottom arc
        painter.drawArc(
            int(stand_x), int(stand_bottom - 4),
            int(stand_width), 8,
            0, -180 * 16
        )
        
        # Stem
        painter.drawLine(
            int(center_x), int(stand_bottom),
            int(center_x), int(center_y + 12)
        )
        
        # Base
        painter.drawLine(
            int(center_x - 5), int(center_y + 12),
            int(center_x + 5), int(center_y + 12)
        )


