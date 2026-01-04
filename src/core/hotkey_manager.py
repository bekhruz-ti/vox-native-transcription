"""
Global hotkey manager for Input-STT application.

Uses the `keyboard` library to register system-wide hotkeys
that work regardless of which application has focus.
"""

import threading
from typing import Callable, Optional

import keyboard
from PySide6.QtCore import QObject, Signal, QMetaObject, Qt, Q_ARG


class HotkeyManager(QObject):
    """
    Manages global keyboard shortcuts.
    
    Uses the `keyboard` library to listen for hotkeys system-wide.
    Emits Qt signals when hotkeys are triggered, ensuring thread-safe
    communication with the UI.
    
    Example:
        manager = HotkeyManager()
        manager.triggered.connect(on_hotkey_pressed)
        manager.register("win+alt+j")
        
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
        self._hook_registered = False
        self._lock = threading.Lock()
    
    @property
    def current_hotkey(self) -> Optional[str]:
        """Get the currently registered hotkey string."""
        return self._current_hotkey
    
    @property
    def is_registered(self) -> bool:
        """Check if a hotkey is currently registered."""
        return self._hook_registered
    
    def register(self, hotkey: str) -> bool:
        """
        Register a global hotkey.
        
        If a hotkey is already registered, it will be unregistered first.
        
        Args:
            hotkey: The hotkey combination (e.g., "ctrl+shift+space").
        
        Returns:
            True if registration succeeded, False otherwise.
        """
        with self._lock:
            # Unregister existing hotkey if any
            if self._hook_registered:
                self._unregister_internal()
            
            try:
                keyboard.add_hotkey(
                    hotkey,
                    self._on_hotkey_pressed,
                    suppress=False  # Don't block the key from other apps
                )
                self._current_hotkey = hotkey
                self._hook_registered = True
                return True
            except Exception as e:
                print(f"Failed to register hotkey '{hotkey}': {e}")
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
        if self._hook_registered and self._current_hotkey:
            try:
                keyboard.remove_hotkey(self._current_hotkey)
            except (KeyError, ValueError):
                # Hotkey might already be removed
                pass
            self._hook_registered = False
            self._current_hotkey = None
    
    def _on_hotkey_pressed(self) -> None:
        """
        Callback invoked by keyboard library when hotkey is pressed.
        
        This runs in the keyboard library's thread, so we use
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


