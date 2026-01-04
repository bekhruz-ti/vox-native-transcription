"""
Toast notification overlay for Input-STT.

A minimal, polished pill-shaped notification that displays:
- "Listening..." state during recording (with animated waveform)
- Transcription text when complete

Features smooth width animation and text fade transitions.
Click anywhere on the toast to copy text and dismiss.
"""

from typing import Optional, List, TYPE_CHECKING
from enum import Enum, auto
import math

from PySide6.QtWidgets import QWidget, QApplication
from PySide6.QtGui import QColor, QPainter, QBrush, QPen, QFont, QFontMetrics
from PySide6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint, QRectF,
    Property, QSequentialAnimationGroup, QParallelAnimationGroup
)

if TYPE_CHECKING:
    from ...providers.base import RealtimeTranscriptionOutput


class ToastState(Enum):
    """Toast display states."""
    LISTENING = auto()
    TRANSCRIPTION = auto()


class ToastNotification(QWidget):
    """
    Minimal pill-shaped toast notification with smooth animations.
    
    Features:
    - Clean dark slate design matching reference
    - Smooth width animation when text changes
    - Text fade in/out transitions
    - Animated waveform bars during listening state
    - Click to copy and dismiss
    """
    
    # Layout constants
    PILL_PADDING = 5           # Padding around pill content
    PILL_PADDING_RIGHT = 18    # Extra right padding for balance
    ICON_CIRCLE_SIZE = 28      # Circular icon wrapper size
    ICON_TEXT_GAP = 10         # Gap between icon circle and text
    MAX_TEXT_WIDTH = 400       # Max text width before truncation
    MARGIN = 24                # Screen edge margin
    FIXED_UI_WIDTH = 5 + 28 + 10 + 18  # padding + icon + gap + right padding = 61
    
    # Colors (from reference HTML)
    PILL_BG = QColor(22, 25, 32)           # #161920 - Dark slate
    ICON_CIRCLE_BG = QColor(30, 38, 57)    # #1e2639 - Slightly lighter
    ACCENT_BLUE = QColor(46, 108, 255)     # #2e6cff - Vivid blue
    TEXT_COLOR = QColor(236, 239, 244)     # #eceff4 - Off-white
    BORDER_COLOR = QColor(255, 255, 255, 8)  # Subtle border
    WARNING_YELLOW = QColor(255, 193, 7)      # Amber yellow for warnings
    
    # Timing
    AUTO_DISMISS_MS = 10000        # 10 seconds for normal transcription
    SHORT_DISMISS_MS = 3000        # 3 seconds for warnings/errors
    SLIDE_DURATION_MS = 200
    WIDTH_ANIM_MS = 400        # Width animation duration
    FADE_DURATION_MS = 150     # Text fade duration
    WAVEFORM_INTERVAL_MS = 50  # Waveform animation tick
    EXIT_COLLAPSE_MS = 500     # Exit: width collapse duration
    EXIT_FADE_MS = 300         # Exit: fade out duration
    
    # Icon-only width for collapsed state (padding + icon + padding)
    ICON_ONLY_WIDTH = 5 + 28 + 5  # 38px
    
    def __init__(self, parent: Optional[QWidget] = None):
        """Initialize the toast notification."""
        super().__init__(parent)
        
        # Window flags for overlay behavior
        self.setWindowFlags(
            Qt.Tool |
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        
        # State
        self._state = ToastState.LISTENING
        self._text = "Listening..."
        self._current_text = ""
        self._had_first_transcription = False  # Track first transition for fade animation
        
        # Animation properties
        self._animated_width = 0.0
        self._text_opacity = 1.0
        self._waveform_phase = 0.0
        self._pill_opacity = 1.0
        self._is_exiting = False
        
        # Set cursor to pointer to indicate clickable
        self.setCursor(Qt.PointingHandCursor)
        
        # Timers
        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self.hide_toast)
        
        # Waveform animation timer
        self._waveform_timer = QTimer(self)
        self._waveform_timer.timeout.connect(self._animate_waveform)
        
        # Animation objects
        self._width_animation: Optional[QPropertyAnimation] = None
        self._opacity_animation: Optional[QPropertyAnimation] = None
        self._fade_in_animation: Optional[QPropertyAnimation] = None
        self._slide_animation: Optional[QPropertyAnimation] = None
        self._exit_collapse_animation: Optional[QPropertyAnimation] = None
        self._exit_fade_animation: Optional[QPropertyAnimation] = None
        
        # Calculate initial size
        self._animated_width = self._calculate_width_for_text(self._text)
        self._update_geometry()
    
    # --- Animated Properties ---
    
    def _get_animated_width(self) -> float:
        return self._animated_width
    
    def _set_animated_width(self, value: float) -> None:
        self._animated_width = value
        self._update_geometry()
    
    animatedWidth = Property(float, _get_animated_width, _set_animated_width)
    
    def _get_text_opacity(self) -> float:
        return self._text_opacity
    
    def _set_text_opacity(self, value: float) -> None:
        self._text_opacity = value
        self.update()
    
    textOpacity = Property(float, _get_text_opacity, _set_text_opacity)
    
    def _get_waveform_phase(self) -> float:
        return self._waveform_phase
    
    def _set_waveform_phase(self, value: float) -> None:
        self._waveform_phase = value
        self.update()
    
    waveformPhase = Property(float, _get_waveform_phase, _set_waveform_phase)
    
    def _get_pill_opacity(self) -> float:
        return self._pill_opacity
    
    def _set_pill_opacity(self, value: float) -> None:
        self._pill_opacity = value
        self.setWindowOpacity(value)
    
    pillOpacity = Property(float, _get_pill_opacity, _set_pill_opacity)
    
    # --- Size Calculations ---
    
    def _calculate_width_for_text(self, text: str) -> float:
        """Calculate the required width for the given text."""
        font = QFont("Segoe UI", 10.5)
        font.setWeight(QFont.Medium)
        fm = QFontMetrics(font)
        
        text_width = min(fm.horizontalAdvance(text), self.MAX_TEXT_WIDTH)
        return self.FIXED_UI_WIDTH + text_width
    
    def _update_geometry(self) -> None:
        """Update widget geometry based on animated width."""
        height = self.PILL_PADDING * 2 + self.ICON_CIRCLE_SIZE
        self.setFixedSize(int(self._animated_width), int(height))
        
        # Update position to keep right-aligned
        screen = QApplication.primaryScreen()
        if screen and self.isVisible():
            screen_geo = screen.availableGeometry()
            new_x = screen_geo.right() - int(self._animated_width) - self.MARGIN
            current_y = self.y()
            self.move(new_x, current_y)
    
    # --- Waveform Animation ---
    
    def _animate_waveform(self) -> None:
        """Update waveform animation phase."""
        self._waveform_phase += 0.15
        if self._waveform_phase > 2 * math.pi:
            self._waveform_phase -= 2 * math.pi
        self.update()
    
    def _start_waveform_animation(self) -> None:
        """Start the waveform pulsing animation."""
        if not self._waveform_timer.isActive():
            self._waveform_timer.start(self.WAVEFORM_INTERVAL_MS)
    
    def _stop_waveform_animation(self) -> None:
        """Stop the waveform animation."""
        self._waveform_timer.stop()
        self._waveform_phase = 0.0
    
    # --- State Changes ---
    
    def show_listening(self) -> None:
        """Show the 'Listening...' state with animated waveform."""
        # Cancel any exit animation in progress
        self._cancel_exit_animation()
        
        # Reset first transcription flag for new session
        self._had_first_transcription = False
        
        new_text = "Listening..."
        
        if self.isVisible() and self._text != new_text and not self._is_exiting:
            # Animate transition
            self._animate_text_change(new_text, ToastState.LISTENING)
        else:
            # First show or recovering from exit
            self._state = ToastState.LISTENING
            self._text = new_text
            self._current_text = ""
            self._animated_width = self._calculate_width_for_text(self._text)
            self._text_opacity = 1.0
            self._update_geometry()
            self._show_at_position()
        
        self._start_waveform_animation()
    
    def show_toast(self, text: str) -> None:
        """Show transcription text with smooth animation."""
        # Cancel any exit animation in progress
        self._cancel_exit_animation()
        
        if not text or not text.strip():
            text = "No Audio Detected"
        
        self._current_text = text.strip()
        
        # Truncate if too long
        display_text = self._current_text
        if len(display_text) > 55:
            display_text = "..." + display_text[-52:]
        
        self._stop_waveform_animation()
        
        if self.isVisible() and self._text != display_text and not self._is_exiting:
            # Animate transition
            self._animate_text_change(display_text, ToastState.TRANSCRIPTION)
        else:
            # First show or same text or recovering from exit
            self._state = ToastState.TRANSCRIPTION
            self._text = display_text
            self._animated_width = self._calculate_width_for_text(self._text)
            self._text_opacity = 1.0
            self._update_geometry()
            self._show_at_position()
        
        # Start auto-dismiss timer (shorter for warning messages)
        dismiss_time = self.SHORT_DISMISS_MS if display_text == "No Audio Detected" else self.AUTO_DISMISS_MS
        self._dismiss_timer.start(dismiss_time)
    
    def update_transcription(self, output: "RealtimeTranscriptionOutput") -> None:
        """
        Update toast with real-time transcription output.
        
        Shows partial transcriptions as they come in, keeping waveform
        animated until COMPLETE status is received.
        
        For CUMULATIVE: Uses latest_transcription directly.
        For INCREMENTAL: Builds cumulative text from last_chunk.
        
        Args:
            output: The RealtimeTranscriptionOutput from the provider.
        """
        # Import here to avoid circular imports
        from ...providers.base import TranscriptionStatus
        
        # Debug logging
        status_str = output.status.value if output.status else "None"
        type_str = output.type.value if output.type else "None"
        chunks_info = f"{len(output.chunks)} chunks" if output.chunks else "no chunks"
        print(f"[TOAST] update_transcription: type={type_str}, status={status_str}, "
              f"latest='{output.latest_transcription[:30] if output.latest_transcription else ''}', "
              f"{chunks_info}")
        
        # Cancel any exit animation in progress
        self._cancel_exit_animation()
        
        # latest_transcription now contains full transcript for BOTH types
        text = output.latest_transcription
        
        if output.status == TranscriptionStatus.COMPLETE:
            # Final transcript - stop waveform, show final text
            print(f"[TOAST] COMPLETE status - stopping waveform animation")
            self._stop_waveform_animation()
            
            # Use final_transcription if available, otherwise latest_transcription
            final_text = output.final_transcription or output.latest_transcription
                
            self._current_text = final_text  # For copy-on-click
            print(f"[TOAST] Final text: '{final_text[:50] if final_text else ''}...'")
            
            # Truncate for display if needed
            display_text = final_text
            if len(display_text) > 55:
                display_text = "..." + display_text[-52:]
            
            if not display_text.strip():
                display_text = "No Audio Detected"
            
            if self.isVisible() and self._text != display_text and not self._is_exiting:
                self._animate_text_change(display_text, ToastState.TRANSCRIPTION)
            else:
                self._state = ToastState.TRANSCRIPTION
                self._text = display_text
                self._animated_width = self._calculate_width_for_text(self._text)
                self._text_opacity = 1.0
                self._update_geometry()
                if not self.isVisible():
                    self._show_at_position()
            
            # Start auto-dismiss timer
            dismiss_time = self.SHORT_DISMISS_MS if display_text == "No Audio Detected" else self.AUTO_DISMISS_MS
            self._dismiss_timer.start(dismiss_time)
            
        elif output.status == TranscriptionStatus.ERROR:
            # Error - hide toast
            self.hide_immediately()
            
        else:
            # Still transcribing (IN_PROGRESS) - keep waveform animating
            self._current_text = text  # Store for copy-on-click
            
            # Truncate for display if needed
            display_text = text
            if len(display_text) > 55:
                display_text = "..." + display_text[-52:]
            
            if not display_text.strip():
                display_text = "Listening..."
            
            # Keep waveform animated while transcribing
            self._start_waveform_animation()
            
            if self.isVisible() and self._text != display_text and not self._is_exiting:
                if not self._had_first_transcription:
                    # First transition (Listening... → text): use fade animation
                    self._had_first_transcription = True
                    self._animate_text_change(display_text, ToastState.LISTENING)
                else:
                    # Subsequent updates: just update text in place with width animation
                    self._text = display_text
                    target_width = self._calculate_width_for_text(self._text)
                    if abs(target_width - self._animated_width) > 5:
                        self._width_animation = QPropertyAnimation(self, b"animatedWidth")
                        self._width_animation.setDuration(self.WIDTH_ANIM_MS // 2)
                        self._width_animation.setStartValue(self._animated_width)
                        self._width_animation.setEndValue(target_width)
                        self._width_animation.setEasingCurve(QEasingCurve.OutCubic)
                        self._width_animation.start()
                    self.update()
            elif not self.isVisible():
                self._state = ToastState.LISTENING
                self._text = display_text
                self._animated_width = self._calculate_width_for_text(self._text)
                self._text_opacity = 1.0
                self._update_geometry()
                self._show_at_position()
            else:
                # Just update text without animation if same or minor change
                if self._text != display_text:
                    self._text = display_text
                    target_width = self._calculate_width_for_text(self._text)
                    if abs(target_width - self._animated_width) > 5:
                        # Animate width change
                        self._width_animation = QPropertyAnimation(self, b"animatedWidth")
                        self._width_animation.setDuration(self.WIDTH_ANIM_MS // 2)
                        self._width_animation.setStartValue(self._animated_width)
                        self._width_animation.setEndValue(target_width)
                        self._width_animation.setEasingCurve(QEasingCurve.OutCubic)
                        self._width_animation.start()
                    self.update()  # Repaint with new text
    
    def _animate_text_change(self, new_text: str, new_state: ToastState) -> None:
        """Animate transition to new text: fade out → change → expand → fade in."""
        target_width = self._calculate_width_for_text(new_text)
        
        # Step 1: Fade out text
        self._opacity_animation = QPropertyAnimation(self, b"textOpacity")
        self._opacity_animation.setDuration(self.FADE_DURATION_MS)
        self._opacity_animation.setStartValue(1.0)
        self._opacity_animation.setEndValue(0.0)
        self._opacity_animation.setEasingCurve(QEasingCurve.OutQuad)
        
        def on_fade_out_finished():
            # Step 2: Update text and state
            self._text = new_text
            self._state = new_state
            
            # Step 3: Animate width
            self._width_animation = QPropertyAnimation(self, b"animatedWidth")
            self._width_animation.setDuration(self.WIDTH_ANIM_MS)
            self._width_animation.setStartValue(self._animated_width)
            self._width_animation.setEndValue(target_width)
            self._width_animation.setEasingCurve(QEasingCurve.OutCubic)
            
            # Step 4: Fade in text (stored as instance var to prevent garbage collection)
            self._fade_in_animation = QPropertyAnimation(self, b"textOpacity")
            self._fade_in_animation.setDuration(self.FADE_DURATION_MS)
            self._fade_in_animation.setStartValue(0.0)
            self._fade_in_animation.setEndValue(1.0)
            self._fade_in_animation.setEasingCurve(QEasingCurve.InQuad)
            
            self._width_animation.finished.connect(self._fade_in_animation.start)
            self._width_animation.start()
        
        self._opacity_animation.finished.connect(on_fade_out_finished)
        self._opacity_animation.start()
    
    def _show_at_position(self) -> None:
        """Position and show the toast with slide-in animation."""
        screen = QApplication.primaryScreen()
        if not screen:
            self.show()
            return
        
        screen_geo = screen.availableGeometry()
        
        # Position: top-right of screen, lower and more to the left
        target_x = screen_geo.right() - int(self._animated_width) - self.MARGIN - 40
        target_y = screen_geo.top() + self.MARGIN + 50
        
        # Start position for slide-in (above screen)
        start_y = screen_geo.top() - self.height()
        
        # Set initial position
        self.move(target_x, start_y)
        self.show()
        self.raise_()
        
        # Animate slide-in
        self._slide_animation = QPropertyAnimation(self, b"pos")
        self._slide_animation.setDuration(self.SLIDE_DURATION_MS)
        self._slide_animation.setStartValue(QPoint(target_x, start_y))
        self._slide_animation.setEndValue(QPoint(target_x, target_y))
        self._slide_animation.setEasingCurve(QEasingCurve.OutCubic)
        self._slide_animation.start()
    
    def hide_toast(self) -> None:
        """Hide the toast with exit animation: collapse text → fade out."""
        if self._is_exiting:
            return  # Already exiting
        
        self._is_exiting = True
        self._dismiss_timer.stop()
        self._stop_waveform_animation()
        
        # Step 1: Fade out text while collapsing width
        self._opacity_animation = QPropertyAnimation(self, b"textOpacity")
        self._opacity_animation.setDuration(self.FADE_DURATION_MS)
        self._opacity_animation.setStartValue(self._text_opacity)
        self._opacity_animation.setEndValue(0.0)
        self._opacity_animation.setEasingCurve(QEasingCurve.OutQuad)
        self._opacity_animation.start()
        
        # Step 2: Collapse width to icon-only
        self._exit_collapse_animation = QPropertyAnimation(self, b"animatedWidth")
        self._exit_collapse_animation.setDuration(self.EXIT_COLLAPSE_MS)
        self._exit_collapse_animation.setStartValue(self._animated_width)
        self._exit_collapse_animation.setEndValue(float(self.ICON_ONLY_WIDTH))
        self._exit_collapse_animation.setEasingCurve(QEasingCurve.InOutCubic)
        
        def on_collapse_finished():
            # Step 3: Fade out the entire pill
            self._exit_fade_animation = QPropertyAnimation(self, b"pillOpacity")
            self._exit_fade_animation.setDuration(self.EXIT_FADE_MS)
            self._exit_fade_animation.setStartValue(1.0)
            self._exit_fade_animation.setEndValue(0.0)
            self._exit_fade_animation.setEasingCurve(QEasingCurve.OutQuad)
            self._exit_fade_animation.finished.connect(self._on_exit_complete)
            self._exit_fade_animation.start()
        
        self._exit_collapse_animation.finished.connect(on_collapse_finished)
        self._exit_collapse_animation.start()
    
    def _on_exit_complete(self) -> None:
        """Called when exit animation is complete."""
        self.hide()
        # Reset state for next show
        self._is_exiting = False
        self._pill_opacity = 1.0
        self.setWindowOpacity(1.0)
        self._text_opacity = 1.0
        self._text = "Listening..."
        self._animated_width = self._calculate_width_for_text(self._text)
    
    def hide_immediately(self) -> None:
        """Hide the toast immediately without animation."""
        self._dismiss_timer.stop()
        self._stop_waveform_animation()
        self._cancel_exit_animation()
        self._is_exiting = False
        self._pill_opacity = 1.0
        self.setWindowOpacity(1.0)
        self._text_opacity = 1.0
        self.hide()
    
    def _cancel_exit_animation(self) -> None:
        """Cancel any ongoing exit animation and reset state."""
        if self._exit_collapse_animation:
            self._exit_collapse_animation.stop()
            self._exit_collapse_animation = None
        if self._exit_fade_animation:
            self._exit_fade_animation.stop()
            self._exit_fade_animation = None
        
        # Reset state
        self._is_exiting = False
        self._pill_opacity = 1.0
        self.setWindowOpacity(1.0)
    
    def mousePressEvent(self, event) -> None:
        """Handle click - copy text and dismiss."""
        if self._current_text:
            clipboard = QApplication.clipboard()
            clipboard.setText(self._current_text)
            print(f"[TOAST] Copied to clipboard: '{self._current_text}'")
        
        self.hide_toast()
    
    def paintEvent(self, event) -> None:
        """Paint the animated pill toast."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        w, h = self.width(), self.height()
        corner_radius = h / 2  # Full pill shape
        
        # Draw shadow layers
        for i in range(4):
            alpha = 25 - i * 6
            offset_y = i + 1
            shadow_color = QColor(0, 0, 0, alpha)
            painter.setBrush(QBrush(shadow_color))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(
                2, offset_y + 2,
                w - 4, h - 2,
                corner_radius, corner_radius
            )
        
        # Draw pill background
        painter.setBrush(QBrush(self.PILL_BG))
        painter.setPen(QPen(self.BORDER_COLOR, 1))
        painter.drawRoundedRect(0, 0, w, h, corner_radius, corner_radius)
        
        # Draw icon circle
        icon_x = self.PILL_PADDING
        icon_y = self.PILL_PADDING
        icon_size = self.ICON_CIRCLE_SIZE
        
        painter.setBrush(QBrush(self.ICON_CIRCLE_BG))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(icon_x, icon_y, icon_size, icon_size)
        
        # Draw waveform bars (animated in listening state)
        self._draw_waveform_icon(painter, icon_x, icon_y, icon_size)
        
        # Draw notification dot
        dot_size = 6
        dot_border = 2
        dot_x = icon_x + icon_size - dot_size - 1
        dot_y = icon_y + 1
        
        painter.setBrush(QBrush(self.PILL_BG))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(
            dot_x - dot_border, dot_y - dot_border,
            dot_size + dot_border * 2, dot_size + dot_border * 2
        )
        
        painter.setBrush(QBrush(self.ACCENT_BLUE))
        painter.drawEllipse(dot_x, dot_y, dot_size, dot_size)
        
        # Draw text with opacity
        text_x = icon_x + icon_size + self.ICON_TEXT_GAP
        text_rect = QRectF(text_x, 0, w - text_x - self.PILL_PADDING_RIGHT, h)
        
        font = QFont("Segoe UI", 10.5)
        font.setWeight(QFont.Medium)
        font.setLetterSpacing(QFont.PercentageSpacing, 100.5)
        painter.setFont(font)
        
        # Apply text opacity (use yellow for warning message)
        if self._text == "No Audio Detected":
            text_color = QColor(self.WARNING_YELLOW)
        else:
            text_color = QColor(self.TEXT_COLOR)
        text_color.setAlphaF(self._text_opacity)
        painter.setPen(text_color)
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, self._text)
        
        painter.end()
    
    def _draw_waveform_icon(self, painter: QPainter, circle_x: float, 
                            circle_y: float, circle_size: float) -> None:
        """Draw animated waveform bars centered in the icon circle."""
        bar_width = 2
        bar_gap = 2
        num_bars = 5
        
        # Base heights
        base_heights = [4, 7, 11, 7, 4]
        
        # Calculate animated heights if in listening state
        if self._state == ToastState.LISTENING:
            heights = []
            for i, base_h in enumerate(base_heights):
                # Create wave effect with phase offset per bar
                phase_offset = i * 0.5
                wave = math.sin(self._waveform_phase + phase_offset)
                # Animate between 30% and 100% of base height
                scale = 0.65 + 0.35 * wave
                heights.append(base_h * scale)
        else:
            heights = base_heights
        
        # Calculate layout
        total_bars_width = num_bars * bar_width + (num_bars - 1) * bar_gap
        center_x = circle_x + circle_size / 2
        center_y = circle_y + circle_size / 2
        start_x = center_x - total_bars_width / 2
        
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(self.ACCENT_BLUE))
        
        for i, bar_height in enumerate(heights):
            bar_x = start_x + i * (bar_width + bar_gap)
            bar_y = center_y - bar_height / 2
            
            painter.drawRoundedRect(
                int(bar_x), int(bar_y),
                bar_width, int(bar_height),
                bar_width / 2, bar_width / 2
            )
    
    def enterEvent(self, event) -> None:
        """Handle mouse enter - pause auto-dismiss."""
        self._dismiss_timer.stop()
        super().enterEvent(event)
    
    def leaveEvent(self, event) -> None:
        """Handle mouse leave - resume auto-dismiss if showing transcription."""
        if self._state == ToastState.TRANSCRIPTION:
            self._dismiss_timer.start(self.AUTO_DISMISS_MS)
        super().leaveEvent(event)


