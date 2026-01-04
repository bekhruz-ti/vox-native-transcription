"""
Settings dialog for Input-STT.

Allows users to configure hotkey bindings and other settings.
"""

from typing import Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QFormLayout, QGroupBox,
    QMessageBox
)
from PySide6.QtGui import QKeySequence, QFont
from PySide6.QtCore import Qt, Signal

from ..config.settings import Settings
from ..core.hotkey_manager import HotkeyManager


class HotkeyEdit(QLineEdit):
    """
    Custom line edit for capturing hotkey combinations.
    
    When focused, captures key presses and displays the hotkey string.
    """
    
    hotkey_changed = Signal(str)
    
    def __init__(self, parent=None):
        """Initialize the hotkey edit."""
        super().__init__(parent)
        self.setReadOnly(True)
        self.setPlaceholderText("Click and press keys...")
        self.setAlignment(Qt.AlignCenter)
        self._hotkey = ""
        self._is_capturing = False
        self._modifiers = set()
        self._key = ""
    
    @property
    def hotkey(self) -> str:
        """Get the current hotkey string."""
        return self._hotkey
    
    def set_hotkey(self, hotkey: str) -> None:
        """Set the hotkey string."""
        self._hotkey = hotkey
        self.setText(hotkey.replace("+", " + ").title())
    
    def focusInEvent(self, event) -> None:
        """Handle focus in - start capturing."""
        super().focusInEvent(event)
        self._is_capturing = True
        self._modifiers = set()
        self._key = ""
        self.setStyleSheet("""
            QLineEdit {
                border: 2px solid #60CDFF;
                background: #2D2D2D;
                color: white;
                padding: 8px;
                border-radius: 4px;
            }
        """)
        self.setText("Press key combination...")
    
    def focusOutEvent(self, event) -> None:
        """Handle focus out - stop capturing."""
        super().focusOutEvent(event)
        self._is_capturing = False
        self.setStyleSheet("""
            QLineEdit {
                border: 1px solid #3D3D3D;
                background: #2D2D2D;
                color: white;
                padding: 8px;
                border-radius: 4px;
            }
        """)
        if self._hotkey:
            self.setText(self._hotkey.replace("+", " + ").title())
        else:
            self.setText("")
    
    def keyPressEvent(self, event) -> None:
        """Handle key press - capture hotkey."""
        if not self._is_capturing:
            super().keyPressEvent(event)
            return
        
        # Track modifiers
        modifiers = event.modifiers()
        key = event.key()
        
        # Build modifier list
        mod_parts = []
        if modifiers & Qt.ControlModifier:
            mod_parts.append("ctrl")
        if modifiers & Qt.AltModifier:
            mod_parts.append("alt")
        if modifiers & Qt.ShiftModifier:
            mod_parts.append("shift")
        if modifiers & Qt.MetaModifier:
            mod_parts.append("win")
        
        # Get key name
        key_name = ""
        if key not in (Qt.Key_Control, Qt.Key_Alt, Qt.Key_Shift, Qt.Key_Meta):
            key_seq = QKeySequence(key)
            key_name = key_seq.toString().lower()
            
            # Special key name mappings
            key_map = {
                "space": "space",
                " ": "space",
                "return": "enter",
                "enter": "enter",
            }
            key_name = key_map.get(key_name, key_name)
        
        # Build hotkey string
        if mod_parts and key_name:
            self._hotkey = "+".join(mod_parts + [key_name])
            self.setText(self._hotkey.replace("+", " + ").title())
            self.hotkey_changed.emit(self._hotkey)
            
            # Auto-defocus after successful capture
            self.clearFocus()
        elif mod_parts:
            # Show current modifiers
            self.setText(" + ".join(mod_parts).title() + " + ...")
    
    def keyReleaseEvent(self, event) -> None:
        """Handle key release."""
        if not self._is_capturing:
            super().keyReleaseEvent(event)


class SettingsDialog(QDialog):
    """
    Settings configuration dialog.
    
    Allows users to:
    - Configure the global hotkey
    - (Future: audio device, language, etc.)
    """
    
    def __init__(
        self,
        settings: Settings,
        hotkey_manager: Optional[HotkeyManager] = None,
        parent=None
    ):
        """
        Initialize the settings dialog.
        
        Args:
            settings: Settings manager instance.
            hotkey_manager: Optional HotkeyManager to update on save.
            parent: Parent widget.
        """
        super().__init__(parent)
        
        self._settings = settings
        self._hotkey_manager = hotkey_manager
        self._original_hotkey = settings.get("hotkey", "win+alt+j")
        
        self.setWindowTitle("Input-STT Settings")
        self.setFixedSize(400, 200)
        self.setModal(True)
        
        # Apply dark theme
        self.setStyleSheet("""
            QDialog {
                background: #1F1F1F;
            }
            QLabel {
                color: white;
            }
            QGroupBox {
                color: white;
                border: 1px solid #3D3D3D;
                border-radius: 4px;
                margin-top: 12px;
                padding-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QPushButton {
                background: #3D3D3D;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background: #4D4D4D;
            }
            QPushButton:pressed {
                background: #5D5D5D;
            }
            QPushButton#saveButton {
                background: #60CDFF;
                color: black;
            }
            QPushButton#saveButton:hover {
                background: #80DDFF;
            }
        """)
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Setup the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Hotkey group
        hotkey_group = QGroupBox("Hotkey")
        hotkey_layout = QFormLayout(hotkey_group)
        
        self._hotkey_edit = HotkeyEdit()
        self._hotkey_edit.set_hotkey(self._original_hotkey)
        self._hotkey_edit.setStyleSheet("""
            QLineEdit {
                border: 1px solid #3D3D3D;
                background: #2D2D2D;
                color: white;
                padding: 8px;
                border-radius: 4px;
            }
        """)
        
        hotkey_label = QLabel("Toggle Recording:")
        hotkey_layout.addRow(hotkey_label, self._hotkey_edit)
        
        # Help text
        help_label = QLabel("Click the field and press your desired key combination")
        help_label.setStyleSheet("color: #808080; font-size: 11px;")
        hotkey_layout.addRow("", help_label)
        
        layout.addWidget(hotkey_group)
        
        layout.addStretch()
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)
        
        save_button = QPushButton("Save")
        save_button.setObjectName("saveButton")
        save_button.clicked.connect(self._on_save)
        button_layout.addWidget(save_button)
        
        layout.addLayout(button_layout)
    
    def _on_save(self) -> None:
        """Handle save button click."""
        new_hotkey = self._hotkey_edit.hotkey
        
        if not new_hotkey:
            QMessageBox.warning(
                self,
                "Invalid Hotkey",
                "Please set a valid hotkey combination."
            )
            return
        
        # Try to register the new hotkey
        if self._hotkey_manager:
            if not self._hotkey_manager.register(new_hotkey):
                QMessageBox.warning(
                    self,
                    "Hotkey Error",
                    f"Could not register hotkey '{new_hotkey}'.\n"
                    "It may be in use by another application."
                )
                # Restore original hotkey
                self._hotkey_manager.register(self._original_hotkey)
                return
        
        # Save settings
        self._settings.set("hotkey", new_hotkey)
        self._settings.save()
        
        self.accept()


