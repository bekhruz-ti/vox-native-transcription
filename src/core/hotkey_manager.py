"""
Global hotkey manager for Input-STT application.

Uses the `pynput` library to register system-wide hotkeys
that work regardless of which application has focus.
Does not require administrator privileges on Windows.
"""

import threading
from typing import Optional

from pynput import keyboard
from PySide6.QtCore import QObject, Signal


class HotkeyManager(QObject):
    """
    Manages global keyboard shortcuts.
    
    Uses the `pynput` library to listen for hotkeys system-wide.
    Emits Qt signals when hotkeys are triggered, ensuring thread-safe
    communication with the UI.
    
    Example:
        manager = HotkeyManager()
        manager.triggered.connect(on_hotkey_pressed)
        manager.register("<cmd>+<alt>+j")
        
        # Later...
        manager.unregister()
    """
    
    # Signal emitted when the registered hotkey is pressed
    triggered = Signal()
    
    def __init__(self, parent: Optional[QObject] = None):
        """
        Initialize the hotkey manager.
        
        Args:
            parent: Optional Qt parent object.
        """
        super().__init__(parent)
        self._current_hotkey: Optional[str] = None
        self._listener: Optional[keyboard.GlobalHotKeys] = None
        self._lock = threading.Lock()
    
    @property
    def current_hotkey(self) -> Optional[str]:
        """Get the currently registered hotkey string."""
        return self._current_hotkey
    
    @property
    def is_registered(self) -> bool:
        """Check if a hotkey is currently registered."""
        return self._listener is not None
    
    def register(self, hotkey: str) -> bool:
        """
        Register a global hotkey.
        
        If a hotkey is already registered, it will be unregistered first.
        
        Args:
            hotkey: The hotkey combination in pynput format (e.g., "<ctrl>+<shift>+j").
        
        Returns:
            True if registration succeeded, False otherwise.
        """
        with self._lock:
            # Unregister existing hotkey if any
            if self._listener is not None:
                self._unregister_internal()
            
            try:
                self._listener = keyboard.GlobalHotKeys({
                    hotkey: self._on_hotkey_pressed
                })
                self._listener.start()
                self._current_hotkey = hotkey
                return True
            except Exception as e:
                print(f"Failed to register hotkey '{hotkey}': {e}")
                self._listener = None
                return False
    
    def unregister(self) -> None:
        """
        Unregister the current hotkey.
        
        Safe to call even if no hotkey is registered.
        """
        with self._lock:
            self._unregister_internal()
    
    def _unregister_internal(self) -> None:
        """Internal unregister without lock (must be called with lock held)."""
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None
            self._current_hotkey = None
    
    def _on_hotkey_pressed(self) -> None:
        """
        Callback invoked by pynput when hotkey is pressed.
        
        This runs in the pynput listener's thread, so we use
        Qt's thread-safe signal emission.
        """
        # Emit signal - this is thread-safe in PySide6
        self.triggered.emit()
    
    def update_hotkey(self, new_hotkey: str) -> bool:
        """
        Update the registered hotkey to a new combination.
        
        Args:
            new_hotkey: The new hotkey combination.
        
        Returns:
            True if the update succeeded, False otherwise.
        """
        return self.register(new_hotkey)
    
    def cleanup(self) -> None:
        """
        Clean up resources.
        
        Should be called when the application is shutting down.
        """
        self.unregister()
