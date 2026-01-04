"""
Real-time microphone transcription test.

This script demonstrates the complete flow:
1. Records audio from the microphone
2. Streams audio chunks to STT provider (OpenAI or ElevenLabs)
3. Prints transcription tokens as they arrive in real-time

Usage:
    python test_realtime_transcription.py --real-time           # OpenAI (default)
    python test_realtime_transcription.py --real-time --openai  # OpenAI explicitly
    python test_realtime_transcription.py --elevenlabs          # ElevenLabs

Requires:
- Valid API key in .env file (OPENAI_API_KEY or ELEVENLABS_API_KEY)
- Microphone access
"""

import os
import sys
import threading
import time
from pathlib import Path

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Add src to path for imports
src_path = str(Path(__file__).parent / "src")
sys.path.insert(0, src_path)

# Import components
from audio.recorder import AudioRecorder
from providers.openai_provider import OpenAIProvider
from providers.elevenlabs_provider import ElevenLabsProvider
from providers.base import GenAIProvider
from utils.audio_utils import AudioConfig


def get_provider(provider_name: str) -> GenAIProvider:
    """
    Get a provider instance by name.
    
    Args:
        provider_name: Either "openai" or "elevenlabs"
    
    Returns:
        A GenAIProvider instance.
    """
    if provider_name == "elevenlabs":
        api_key = os.getenv("ELEVENLABS_API_KEY")
        if not api_key:
            raise ValueError("ELEVENLABS_API_KEY not set in .env file")
        return ElevenLabsProvider(api_key=api_key)
    else:  # Default to OpenAI
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key or api_key == "your_openai_api_key_here":
            raise ValueError("OPENAI_API_KEY not set in .env file")
        return OpenAIProvider(api_key=api_key)


def test_audio_devices():
    """Test that we can list audio devices."""
    print("\n" + "=" * 60)
    print("Available Audio Input Devices")
    print("=" * 60)
    
    devices = AudioRecorder.get_audio_devices()
    
    if not devices:
        print("No audio input devices found!")
        return False
    
    for device in devices:
        print(f"  [{device['index']}] {device['name']}")
        print(f"      Channels: {device['channels']}, Sample Rate: {device['sample_rate']} Hz")
    
    default = AudioRecorder.get_default_device()
    if default:
        print(f"\nDefault device: [{default['index']}] {default['name']}")
    
    return True


def test_basic_recording():
    """Test basic audio recording to file."""
    print("\n" + "=" * 60)
    print("Testing Basic Recording (3 seconds)")
    print("=" * 60)
    
    recorder = AudioRecorder()
    output_path = "tests/fixtures/test_recording.wav"
    
    print("Recording for 3 seconds... Speak into your microphone!")
    
    try:
        path = recorder.record_to_file(output_path, max_duration=3.0)
        file_size = Path(path).stat().st_size
        print(f"✅ Recording saved to: {path}")
        print(f"   File size: {file_size / 1024:.1f} KB")
        return True
    except Exception as e:
        print(f"❌ Recording failed: {e}")
        return False


def test_streaming_recording():
    """Test streaming audio recording."""
    print("\n" + "=" * 60)
    print("Testing Streaming Recording (5 seconds)")
    print("=" * 60)
    
    recorder = AudioRecorder()
    
    print("Recording audio stream for 5 seconds...")
    
    chunk_count = 0
    total_bytes = 0
    
    recorder.start()
    start_time = time.time()
    
    try:
        for chunk in recorder.record():
            chunk_count += 1
            total_bytes += len(chunk)
            
            # Print progress every 10 chunks
            if chunk_count % 10 == 0:
                elapsed = time.time() - start_time
                print(f"  Received {chunk_count} chunks ({total_bytes / 1024:.1f} KB) in {elapsed:.1f}s")
            
            # Stop after 5 seconds
            if time.time() - start_time >= 5.0:
                break
    finally:
        recorder.stop()
    
    print(f"\n✅ Streaming test complete:")
    print(f"   Total chunks: {chunk_count}")
    print(f"   Total data: {total_bytes / 1024:.1f} KB")
    print(f"   Avg chunk size: {total_bytes / chunk_count:.0f} bytes")
    
    return chunk_count > 0


def test_realtime_transcription(provider_name: str = "openai"):
    """Test real-time transcription with specified provider."""
    print("\n" + "=" * 60)
    print(f"Testing Real-time Transcription ({provider_name.upper()})")
    print("=" * 60)
    
    # Get provider
    try:
        provider = get_provider(provider_name)
    except ValueError as e:
        print(f"❌ {e}")
        return False
    
    print(f"Provider: {provider.name}")
    print("This test will:")
    print("  1. Record from your microphone for up to 10 seconds")
    print(f"  2. Stream audio to {provider.name} API")
    print("  3. Print transcription as it arrives")
    print("\nPress Enter at any time to stop recording.\n")
    
    # Create components
    recorder = AudioRecorder()
    
    # Flag to signal stop
    stop_flag = threading.Event()
    
    def wait_for_enter():
        """Wait for Enter key press."""
        input()
        stop_flag.set()
        recorder.stop()
    
    # Start Enter key listener in background
    input_thread = threading.Thread(target=wait_for_enter, daemon=True)
    input_thread.start()
    
    print("-" * 40)
    print("🎤 Recording... (speak now)")
    print("-" * 40)
    
    # Start recording
    recorder.start()
    
    def audio_generator():
        """Generate audio chunks with timeout."""
        start_time = time.time()
        for chunk in recorder.record():
            yield chunk
            # Stop after 10 seconds max
            if time.time() - start_time >= 10.0 or stop_flag.is_set():
                break
    
    # Transcribe in real-time
    last_text = ""
    final_text = ""
    try:
        for text in provider.transcribe_realtime(audio_generator()):
            if text != last_text:
                print(f"\n📝 {text}", end="", flush=True)
                last_text = text
                final_text = text  # Keep track of the last (most complete) transcript
    except Exception as e:
        print(f"\n❌ Transcription error: {e}")
        return False
    finally:
        recorder.stop()
    
    print("\n" + "-" * 40)
    
    if final_text:
        print(f"\n✅ Full transcription: {final_text}")
        return True
    else:
        print("\n⚠️ No transcription received (possibly no speech detected)")
        return True  # Not a failure, just no speech


def test_batch_transcription_with_recording(provider_name: str = "openai"):
    """Test recording then batch transcription."""
    print("\n" + "=" * 60)
    print(f"Testing Record + Batch Transcription ({provider_name.upper()})")
    print("=" * 60)
    
    # Get provider
    try:
        provider = get_provider(provider_name)
    except ValueError as e:
        print(f"❌ {e}")
        return False
    
    recorder = AudioRecorder()
    
    output_path = "tests/fixtures/batch_test.wav"
    
    print("Recording for 5 seconds... Speak clearly!")
    
    try:
        # Record to file
        path = recorder.record_to_file(output_path, max_duration=5.0)
        print(f"Recording saved: {path}")
        
        # Transcribe
        print("Transcribing...")
        result = provider.transcribe_batch(path)
        
        print(f"\n✅ Transcription: {result}")
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def main():
    """Run all audio and transcription tests."""
    print("=" * 60)
    print("Audio Recording & Real-time Transcription Tests")
    print("=" * 60)
    
    results = []
    
    # Test 1: List audio devices
    results.append(("Audio Devices", test_audio_devices()))
    
    # Test 2: Basic recording
    results.append(("Basic Recording", test_basic_recording()))
    
    # Test 3: Streaming recording
    results.append(("Streaming Recording", test_streaming_recording()))
    
    # Test 4: Batch transcription with recording
    results.append(("Batch Transcription", test_batch_transcription_with_recording()))
    
    # Test 5: Real-time transcription (interactive)
    print("\n" + "=" * 60)
    print("Ready for Real-time Transcription Test?")
    print("This test is interactive and requires you to speak.")
    print("=" * 60)
    response = input("Run real-time test? [Y/n]: ").strip().lower()
    
    if response in ("", "y", "yes"):
        results.append(("Real-time Transcription", test_realtime_transcription()))
    else:
        print("Skipping real-time test.")
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    for name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"  {name}: {status}")
    
    all_passed = all(passed for _, passed in results)
    print("\n" + ("✅ All tests passed!" if all_passed else "❌ Some tests failed"))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Audio recording and transcription tests")
    parser.add_argument("--real-time", action="store_true", help="Run only the real-time transcription test")
    parser.add_argument("--openai", action="store_true", help="Use OpenAI provider (default)")
    parser.add_argument("--elevenlabs", action="store_true", help="Use ElevenLabs provider")
    args = parser.parse_args()
    
    # Determine provider
    if args.elevenlabs:
        provider_name = "elevenlabs"
    else:
        provider_name = "openai"  # Default
    
    if args.real_time or args.elevenlabs:
        # Run real-time test with selected provider
        test_realtime_transcription(provider_name)
    else:
        main()

