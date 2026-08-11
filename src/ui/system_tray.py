"""
System tray icon and menu for Input-STT.

Provides a persistent tray icon with context menu for controlling
the application and accessing settings.
"""

from typing import Optional

from PySide6.QtWidgets import QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QBrush, QPen
from PySide6.QtCore import QObject, Signal, QTimer, Qt, QSize

# Bar geometry is relative to a 48px reference (the tray size) so the same mark
# can be rendered at any resolution for the application icon.
_REFERENCE_SIZE = 48
_BAR_WIDTH = 5
_BAR_GAP = 2
_BAR_HEIGHT_RATIOS = (0.35, 0.65, 1.0, 0.65, 0.35)


def render_waveform_pixmap(size: int, color: QColor, bg_color: QColor) -> QPixmap:
    """
    Draw the waveform-in-a-circle mark shared by the tray and the app icon.

    Args:
        size: Output edge length in pixels.
        color: Waveform bar colour.
        bg_color: Circular background colour.

    Returns:
        The rendered pixmap with a transparent surround.
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    painter.setBrush(QBrush(bg_color))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(0, 0, size, size)

    scale = size / _REFERENCE_SIZE
    bar_width = max(1, round(_BAR_WIDTH * scale))
    bar_gap = max(1, round(_BAR_GAP * scale))
    max_height = size * 0.75
    num_bars = len(_BAR_HEIGHT_RATIOS)

    total_bars_width = num_bars * bar_width + (num_bars - 1) * bar_gap
    start_x = size / 2 - total_bars_width / 2

    painter.setBrush(QBrush(color))
    for i, height_ratio in enumerate(_BAR_HEIGHT_RATIOS):
        bar_height = int(max_height * height_ratio)
        bar_x = int(start_x + i * (bar_width + bar_gap))
        bar_y = int(size / 2 - bar_height / 2)
        painter.drawRoundedRect(
            bar_x, bar_y,
            bar_width, bar_height,
            bar_width / 2, bar_width / 2
        )

    painter.end()
    return pixmap


class SystemTray(QSystemTrayIcon):
    """
    System tray icon with context menu.
    
    States:
        - Idle: Blue waveform icon (matches toast design)
        - Recording: Red waveform icon (pulsing animation)
        - Processing: Blue waveform icon
    
    Signals:
        toggle_recording_requested: User wants to start/stop recording.
        settings_requested: User wants to open settings.
        exit_requested: User wants to exit the application.
    """
    
    # Signals
    toggle_recording_requested = Signal()
    settings_requested = Signal()
    exit_requested = Signal()
    
    # Icon colors (matching toast design)
    COLOR_IDLE = QColor(46, 108, 255)          # #2e6cff - Vivid blue (same as toast)
    COLOR_RECORDING = QColor(239, 68, 68)      # Red
    COLOR_RECORDING_DIM = QColor(185, 55, 55)  # Dimmer red for pulse
    COLOR_PROCESSING = QColor(46, 108, 255)    # Blue
    BG_COLOR = QColor(30, 38, 57)              # #1e2639 - Dark circle bg
    
    def __init__(self, parent: Optional[QObject] = None):
        """Initialize the system tray."""
        super().__init__(parent)
        
        self._is_recording = False
        self._is_processing = False
        self._pulse_state = False
        
        # Create icons with waveform design
        self._icon_idle = self._create_waveform_icon(self.COLOR_IDLE)
        self._icon_recording = self._create_waveform_icon(self.COLOR_RECORDING)
        self._icon_recording_dim = self._create_waveform_icon(self.COLOR_RECORDING_DIM)
        self._icon_processing = self._create_waveform_icon(self.COLOR_PROCESSING)
        
        # Set initial icon
        self.setIcon(self._icon_idle)
        self.setToolTip("Input-STT - Press hotkey to record")
        
        # Create context menu
        self._create_menu()
        
        # Pulse animation timer
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._on_pulse_tick)
        
        # Handle activation (clicks)
        self.activated.connect(self._on_activated)
    
    def _create_waveform_icon(self, color: QColor, size: int = 48) -> QIcon:
        """
        Create a waveform icon matching the toast design.
        
        Args:
            color: Waveform bar color.
            size: Icon size in pixels.
        
        Returns:
            QIcon with the waveform design.
        """
        return QIcon(render_waveform_pixmap(size, color, self.BG_COLOR))
    
    def _create_menu(self) -> None:
        """Create the context menu."""
        menu = QMenu()
        
        # Start/Stop recording action
        self._action_toggle = menu.addAction("Start Recording")
        self._action_toggle.triggered.connect(self._on_toggle_clicked)
        
        menu.addSeparator()
        
        # Settings action
        action_settings = menu.addAction("Settings...")
        action_settings.triggered.connect(self.settings_requested.emit)
        
        menu.addSeparator()
        
        # Exit action
        action_exit = menu.addAction("Exit")
        action_exit.triggered.connect(self.exit_requested.emit)
        
        self.setContextMenu(menu)
    
    def set_recording_state(self, is_recording: bool) -> None:
        """
        Set the recording state.
        
        Args:
            is_recording: True if currently recording.
        """
        self._is_recording = is_recording
        self._is_processing = False
        
        if is_recording:
            self._action_toggle.setText("Stop Recording")
            self.setToolTip("Input-STT - Recording...")
            self.setIcon(self._icon_recording)
            
            # Start pulse animation
            self._pulse_timer.start(500)  # 500ms interval
        else:
            self._action_toggle.setText("Start Recording")
            self.setToolTip("Input-STT - Press hotkey to record")
            self.setIcon(self._icon_idle)
            
            # Stop pulse animation
            self._pulse_timer.stop()
            self._pulse_state = False
    
    def set_processing_state(self, is_processing: bool) -> None:
        """
        Set the processing state.
        
        Args:
            is_processing: True if currently processing transcription.
        """
        if is_processing:
            self._is_recording = False
            self._is_processing = True
            self._pulse_timer.stop()
            
            self.setIcon(self._icon_processing)
            self.setToolTip("Input-STT - Processing...")
        else:
            self._is_processing = False
            if not self._is_recording:
                self.setIcon(self._icon_idle)
                self.setToolTip("Input-STT - Press hotkey to record")
    
    def _on_pulse_tick(self) -> None:
        """Handle pulse animation tick."""
        if self._is_recording:
            self._pulse_state = not self._pulse_state
            if self._pulse_state:
                self.setIcon(self._icon_recording_dim)
            else:
                self.setIcon(self._icon_recording)
    
    def _on_toggle_clicked(self) -> None:
        """Handle toggle menu action click."""
        self.toggle_recording_requested.emit()
    
    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """Handle tray icon activation (clicks)."""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            # Double-click toggles recording
            self.toggle_recording_requested.emit()


