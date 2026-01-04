"""
Focus detection for determining if a text input field is active.

Uses Windows UI Automation to detect whether the currently focused
element is a text input field where text can be typed.
"""

from typing import Optional
import sys


class FocusDetector:
    """
    Detects whether a text input field is currently focused.
    
    Uses Windows UI Automation API to query the focused element
    and determine if it supports text input.
    
    Example:
        detector = FocusDetector()
        
        if detector.is_text_input_focused():
            # Inject text directly
            injector.inject(text)
        else:
            # Show toast notification instead
            toast.show(text)
    """
    
    # Control types that typically support text input
    TEXT_CONTROL_TYPES = {
        "EditControl",
        "DocumentControl", 
        "TextControl",
    }
    
    def __init__(self):
        """Initialize the focus detector."""
        self._uiautomation = None
        self._available = False
        self._init_automation()
    
    def _init_automation(self) -> None:
        """Initialize the UI Automation library."""
        if sys.platform != "win32":
            self._available = False
            return
        
        try:
            import uiautomation as auto
            self._uiautomation = auto
            self._available = True
        except ImportError:
            self._available = False
            print("Warning: uiautomation not available. Focus detection disabled.")
    
    @property
    def is_available(self) -> bool:
        """Check if focus detection is available on this system."""
        return self._available
    
    def is_text_input_focused(self) -> bool:
        """
        Check if a text input field is currently focused.
        
        Returns:
            True if a text input field is focused, False otherwise.
            Returns False if focus detection is unavailable or fails.
        """
        if not self._available:
            return False
        
        try:
            element_info = self.get_focused_element_info()
            if element_info is None:
                return False
            
            control_type = element_info.get("control_type", "")
            
            # Check if control type is a text input type
            if control_type in self.TEXT_CONTROL_TYPES:
                return True
            
            # Also check for editable property
            if element_info.get("is_keyboard_focusable", False):
                # Some controls are marked as keyboard focusable and can receive text
                # Check if it has value pattern (can hold text)
                if element_info.get("has_value_pattern", False):
                    return True
            
            return False
            
        except Exception as e:
            # Fail silently - return False to trigger toast fallback
            print(f"Focus detection error: {e}")
            return False
    
    def get_focused_element_info(self) -> Optional[dict]:
        """
        Get information about the currently focused UI element.
        
        Returns:
            Dictionary with element information, or None if unavailable.
            
            Keys:
                - name: Element name/label
                - control_type: Type of control (e.g., "EditControl")
                - class_name: Windows class name
                - automation_id: Automation identifier
                - is_keyboard_focusable: Whether element can receive keyboard input
                - has_value_pattern: Whether element supports ValuePattern
        """
        if not self._available:
            return None
        
        try:
            auto = self._uiautomation
            
            # Get the focused control
            focused = auto.GetFocusedControl()
            
            if focused is None:
                return None
            
            # Extract control information
            info = {
                "name": focused.Name or "",
                "control_type": focused.ControlTypeName or "",
                "class_name": focused.ClassName or "",
                "automation_id": focused.AutomationId or "",
                "is_keyboard_focusable": False,
                "has_value_pattern": False,
            }
            
            # Check if keyboard focusable
            try:
                info["is_keyboard_focusable"] = focused.IsKeyboardFocusable
            except Exception:
                pass
            
            # Check for ValuePattern support (indicates text can be entered)
            try:
                # Try to get ValuePattern - if it exists, element can hold text
                value_pattern = focused.GetValuePattern()
                info["has_value_pattern"] = value_pattern is not None
            except Exception:
                pass
            
            return info
            
        except Exception as e:
            print(f"Error getting focused element: {e}")
            return None
    
    def get_focused_app_name(self) -> Optional[str]:
        """
        Get the name of the application that has focus.
        
        Returns:
            Application name or window title, or None if unavailable.
        """
        if not self._available:
            return None
        
        try:
            auto = self._uiautomation
            
            # Get the foreground window
            foreground = auto.GetForegroundControl()
            
            if foreground is None:
                return None
            
            return foreground.Name or None
            
        except Exception:
            return None


