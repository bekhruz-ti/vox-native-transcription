"""
Integration test for OpenAI transcription.

This script tests the batch transcription with a real audio file.
Requires a valid OPENAI_API_KEY in .env file.
"""

import os
import sys
import urllib.request
from pathlib import Path

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from providers.openai_provider import OpenAIProvider


def download_sample_audio():
    """Download a sample audio file for testing."""
    # Use a public domain sample audio from the web
    # This is a sample from OpenAI's Whisper demo
    sample_url = "https://github.com/openai/whisper/raw/main/tests/jfk.flac"
    
    # Alternative: use a simple text-to-speech sample
    # This is a NASA public domain audio clip
    sample_url = "https://www.nasa.gov/wp-content/uploads/2015/01/590325main_ringtone_kennedy_702702.mp3"
    
    output_path = Path("tests/fixtures/sample.mp3")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    if not output_path.exists():
        print(f"Downloading sample audio from {sample_url}...")
        try:
            urllib.request.urlretrieve(sample_url, output_path)
            print(f"Downloaded to {output_path}")
        except Exception as e:
            print(f"Failed to download sample audio: {e}")
            # Create a fallback: try another source
            alt_url = "https://filesamples.com/samples/audio/mp3/sample1.mp3"
            try:
                urllib.request.urlretrieve(alt_url, output_path)
                print(f"Downloaded from fallback to {output_path}")
            except Exception as e2:
                print(f"Fallback also failed: {e2}")
                return None
    
    return output_path


def test_batch_transcription():
    """Test batch transcription with a real audio file."""
    print("\n" + "=" * 60)
    print("Testing Batch Transcription (Whisper API)")
    print("=" * 60)
    
    # Download sample audio
    audio_path = download_sample_audio()
    if not audio_path or not audio_path.exists():
        print("❌ Could not get sample audio file")
        return False
    
    print(f"Using audio file: {audio_path}")
    print(f"File size: {audio_path.stat().st_size / 1024:.1f} KB")
    
    try:
        # Create provider
        provider = OpenAIProvider()
        print(f"Provider: {provider.name}")
        
        # Check availability
        print("Checking API availability...")
        if provider.is_available():
            print("✅ API is available")
        else:
            print("⚠️ API availability check failed (but may still work)")
        
        # Transcribe
        print("\nTranscribing audio...")
        result = provider.transcribe_batch(str(audio_path))
        
        print("\n" + "-" * 40)
        print("Transcription Result:")
        print("-" * 40)
        print(result)
        print("-" * 40)
        
        print("\n✅ Batch transcription successful!")
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return False


def main():
    """Run integration tests."""
    print("=" * 60)
    print("OpenAI Transcription Integration Test")
    print("=" * 60)
    
    # Check for API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "your_openai_api_key_here":
        print("❌ OPENAI_API_KEY not set in .env file")
        print("Please add your OpenAI API key to the .env file")
        return
    
    print(f"✅ API key found (starts with: {api_key[:8]}...)")
    
    # Run tests
    results = []
    results.append(("Batch Transcription", test_batch_transcription()))
    
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
    main()

