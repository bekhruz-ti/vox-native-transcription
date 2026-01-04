"""
Simple non-interactive real-time transcription test.

Records from microphone for 10 seconds and transcribes in real-time.
No user input required - just run and speak!
"""

import os
import sys
import time
from pathlib import Path

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Add src to path (go up one level from tests/)
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from audio.recorder import AudioRecorder
from providers.openai_provider import OpenAIProvider


def main():
    """Run real-time transcription test."""
    print("=" * 60)
    print("Real-time Transcription Test (10 seconds)")
    print("=" * 60)
    
    # Check for API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "your_openai_api_key_here":
        print("ERROR: OPENAI_API_KEY not set in .env file")
        return
    
    print(f"API key found: {api_key[:12]}...")
    
    # Initialize components
    recorder = AudioRecorder()
    provider = OpenAIProvider()
    
    # Show device info
    default_device = recorder.get_default_device()
    if default_device:
        print(f"Using microphone: {default_device['name']}")
    
    print("\n" + "-" * 60)
    print("RECORDING NOW - Speak into your microphone!")
    print("-" * 60 + "\n")
    
    # Start recording
    recorder.start()
    
    def audio_generator():
        """Generate audio chunks for 10 seconds."""
        start_time = time.time()
        chunk_count = 0
        
        for chunk in recorder.record():
            chunk_count += 1
            elapsed = time.time() - start_time
            
            # Print progress dots every second
            if chunk_count % 10 == 0:
                remaining = 10.0 - elapsed
                print(f"[Recording: {remaining:.0f}s remaining]", end="\r")
            
            yield chunk
            
            # Stop after 10 seconds
            if elapsed >= 10.0:
                break
        
        print("\n\nProcessing transcription...")
    
    # Collect transcription
    transcription_parts = []
    
    try:
        print("Transcription output:")
        print("-" * 40)
        
        for text in provider.transcribe_realtime(audio_generator()):
            print(text, end="", flush=True)
            transcription_parts.append(text)
        
        print("\n" + "-" * 40)
        
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        recorder.stop()
    
    # Summary
    if transcription_parts:
        full_text = "".join(transcription_parts)
        print(f"\nFull transcription: {full_text}")
        print("\n[SUCCESS] Real-time transcription completed!")
    else:
        print("\n[WARNING] No transcription received.")
        print("This could mean:")
        print("  - No speech was detected")
        print("  - Microphone volume too low")
        print("  - API connection issue")


if __name__ == "__main__":
    main()

