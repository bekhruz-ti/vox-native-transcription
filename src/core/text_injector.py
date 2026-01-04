"""
Text injection for simulating keyboard input.

Uses pynput to type text into the currently focused application,
supporting both complete text injection and incremental (real-time) mode.
"""

import time
import threading
from typing import Optional

from pynput.keyboard import Controller, Key


class TextInjector:
    """
    Injects text into applications by simulating keyboard input.
    
    Supports two modes:
    1. Complete injection: Type entire text at once
    2. Incremental injection: Type only new characters (for real-time STT)
    
    Example:
        injector = TextInjector()
        
        # Complete mode
        injector.inject("Hello, world!")
        
        # Incremental mode (for real-time transcription)
        injector.inject_incremental("Hello")      # Types "Hello"
        injector.inject_incremental("Hello, ")    # Types ", "
        injector.inject_incremental("Hello, world")  # Types "world"
        injector.reset_incremental()  # Reset for next session
    """
    
    def __init__(self, typing_delay: float = 0.0):
        """
        Initialize the text injector.
        
        Args:
            typing_delay: Delay in seconds between characters.
                         0 = fastest (may cause issues in some apps).
                         0.001-0.005 = safer for most applications.
        """
        self._keyboard = Controller()
        self._typing_delay = typing_delay
        self._last_injected_text = ""
        self._lock = threading.Lock()
    
    @property
    def typing_delay(self) -> float:
        """Get the current typing delay in seconds."""
        return self._typing_delay
    
    @typing_delay.setter
    def typing_delay(self, value: float) -> None:
        """Set the typing delay in seconds."""
        self._typing_delay = max(0.0, value)
    
    def inject(self, text: str) -> None:
        """
        Inject complete text by simulating keyboard input.
        
        Types the entire text string into the currently focused element.
        
        Args:
            text: The text to type.
        """
        if not text:
            return
        
        with self._lock:
            if self._typing_delay > 0:
                # Type character by character with delay
                for char in text:
                    self._type_char(char)
                    time.sleep(self._typing_delay)
            else:
                # Type all at once (fastest)
                self._keyboard.type(text)
    
    def inject_incremental(self, cumulative_text: str) -> str:
        """
        Inject only the new portion of text (for real-time mode).
        
        Compares the new cumulative text with what was previously injected
        and types only the difference.
        
        Args:
            cumulative_text: The complete transcription so far.
        
        Returns:
            The delta text that was actually typed.
        """
        with self._lock:
            # Calculate what's new
            if cumulative_text.startswith(self._last_injected_text):
                delta = cumulative_text[len(self._last_injected_text):]
            else:
                # Text doesn't start with previous - this might be a correction
                # For now, just type the new parts
                # More sophisticated handling could use diff algorithms
                delta = cumulative_text[len(self._last_injected_text):]
            
            if delta:
                # Type the new characters
                if self._typing_delay > 0:
                    for char in delta:
                        self._type_char(char)
                        time.sleep(self._typing_delay)
                else:
                    self._keyboard.type(delta)
                
                self._last_injected_text = cumulative_text
            
            return delta
    
    def reset_incremental(self) -> None:
        """
        Reset the incremental injection state.
        
        Call this when starting a new recording/transcription session.
        """
        with self._lock:
            self._last_injected_text = ""
    
    def _type_char(self, char: str) -> None:
        """
        Type a single character.
        
        Handles special characters and newlines.
        
        Args:
            char: The character to type.
        """
        if char == "\n":
            self._keyboard.press(Key.enter)
            self._keyboard.release(Key.enter)
        elif char == "\t":
            self._keyboard.press(Key.tab)
            self._keyboard.release(Key.tab)
        else:
            self._keyboard.type(char)
    
    def press_key(self, key: Key) -> None:
        """
        Press and release a special key.
        
        Args:
            key: The pynput Key to press.
        """
        self._keyboard.press(key)
        self._keyboard.release(key)
    
    def backspace(self, count: int = 1) -> None:
        """
        Simulate backspace key presses.
        
        Useful for correcting text if transcription changes.
        
        Args:
            count: Number of backspaces to send.
        """
        for _ in range(count):
            self.press_key(Key.backspace)
            if self._typing_delay > 0:
                time.sleep(self._typing_delay)
    
    @property
    def last_injected_text(self) -> str:
        """Get the last injected text (for incremental mode)."""
        return self._last_injected_text


