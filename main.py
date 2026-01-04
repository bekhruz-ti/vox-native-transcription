#!/usr/bin/env python3
"""
Input-STT: Desktop Speech-to-Text Tool

A Windows-native STT application that:
1. Listens for a global hotkey to start/stop recording
2. Transcribes speech using OpenAI Whisper
3. Injects text into the focused application or shows a toast notification

Usage:
    python main.py

Requirements:
    - Windows 10/11
    - OpenAI API key set in OPENAI_API_KEY environment variable
    - Microphone access

Configuration:
    Settings are stored in %APPDATA%/InputSTT/settings.json
"""

import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()


def check_requirements() -> bool:
    """Check that all requirements are met."""
    # Check for Windows
    if sys.platform != "win32":
        print("Warning: This application is designed for Windows.")
        print("Some features may not work on other platforms.")
    
    # Check for OpenAI API key
    if not os.getenv("OPENAI_API_KEY"):
        print("Warning: OPENAI_API_KEY environment variable not set.")
        print("Please set it or create a .env file with your API key.")
        print("The application will start but transcription won't work.")
    
    return True


def main() -> int:
    """
    Main entry point for Input-STT.
    
    Returns:
        Exit code (0 for success, non-zero for error).
    """
    print("Starting Input-STT...")
    
    # Check requirements
    if not check_requirements():
        return 1
    
    try:
        from src.ui.app import run_application
        return run_application()
    except ImportError as e:
        print(f"Import error: {e}")
        print("\nPlease install dependencies:")
        print("  pip install -r requirements.txt")
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        return 0
    except Exception as e:
        print(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())


