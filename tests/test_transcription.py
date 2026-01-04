"""
Tests for transcription providers.

These tests require a valid OpenAI API key to run integration tests.
Unit tests use mocking to avoid API calls.
"""

import os
import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

# Add src to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from providers.base import GenAIProvider, TranscriptionError
from providers.openai_provider import OpenAIProvider


class TestGenAIProviderInterface:
    """Test that the abstract interface is properly defined."""
    
    def test_cannot_instantiate_abstract_class(self):
        """Verify GenAIProvider cannot be instantiated directly."""
        with pytest.raises(TypeError):
            GenAIProvider()
    
    def test_transcription_error_creation(self):
        """Test TranscriptionError exception."""
        error = TranscriptionError(
            message="Test error",
            provider="TestProvider",
            original_error=ValueError("Original")
        )
        
        assert "Test error" in str(error)
        assert "TestProvider" in str(error)
        assert error.provider == "TestProvider"
        assert isinstance(error.original_error, ValueError)


class TestOpenAIProvider:
    """Tests for OpenAIProvider."""
    
    def test_requires_api_key(self):
        """Verify that API key is required."""
        # Temporarily clear the env var if set
        original_key = os.environ.pop("OPENAI_API_KEY", None)
        
        try:
            with pytest.raises(ValueError, match="API key is required"):
                OpenAIProvider(api_key=None)
        finally:
            if original_key:
                os.environ["OPENAI_API_KEY"] = original_key
    
    def test_rejects_placeholder_key(self):
        """Verify that placeholder API key is rejected."""
        with pytest.raises(ValueError, match="API key is required"):
            OpenAIProvider(api_key="your_openai_api_key_here")
    
    @patch("providers.openai_provider.OpenAI")
    def test_provider_name(self, mock_openai):
        """Test provider name property."""
        provider = OpenAIProvider(api_key="sk-test-key")
        assert provider.name == "OpenAI"
    
    @patch("providers.openai_provider.OpenAI")
    def test_batch_transcription_file_not_found(self, mock_openai):
        """Test error handling for missing file."""
        provider = OpenAIProvider(api_key="sk-test-key")
        
        with pytest.raises(FileNotFoundError):
            provider.transcribe_batch("/nonexistent/file.wav")
    
    @patch("providers.openai_provider.OpenAI")
    def test_batch_transcription_unsupported_format(self, mock_openai, tmp_path):
        """Test error handling for unsupported format."""
        # Create a temp file with unsupported extension
        test_file = tmp_path / "test.xyz"
        test_file.write_text("dummy content")
        
        provider = OpenAIProvider(api_key="sk-test-key")
        
        with pytest.raises(ValueError, match="Unsupported audio format"):
            provider.transcribe_batch(str(test_file))
    
    @patch("providers.openai_provider.OpenAI")
    def test_batch_transcription_success(self, mock_openai, tmp_path):
        """Test successful batch transcription."""
        # Create a mock WAV file
        test_file = tmp_path / "test.wav"
        test_file.write_bytes(b"RIFF" + b"\x00" * 100)  # Minimal WAV-like content
        
        # Mock the API response
        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = "Hello, world!"
        mock_openai.return_value = mock_client
        
        provider = OpenAIProvider(api_key="sk-test-key")
        result = provider.transcribe_batch(str(test_file))
        
        assert result == "Hello, world!"
        mock_client.audio.transcriptions.create.assert_called_once()


class TestAudioUtils:
    """Tests for audio utility functions."""
    
    def test_audio_config_defaults(self):
        """Test default audio configuration."""
        from utils.audio_utils import AudioConfig
        
        config = AudioConfig()
        assert config.sample_rate == 16000
        assert config.channels == 1
        assert config.chunk_duration_ms == 100
    
    def test_chunk_size_calculation(self):
        """Test chunk size calculation."""
        from utils.audio_utils import AudioConfig
        
        config = AudioConfig(sample_rate=16000, chunk_duration_ms=100)
        # 16000 samples/sec * 0.1 sec = 1600 samples
        assert config.chunk_size == 1600
        # 1600 samples * 1 channel * 2 bytes = 3200 bytes
        assert config.chunk_bytes == 3200
    
    def test_validate_audio_format_missing_file(self):
        """Test validation of missing file."""
        from utils.audio_utils import validate_audio_format
        
        is_valid, error = validate_audio_format("/nonexistent/file.wav")
        assert not is_valid
        assert "not found" in error.lower()
    
    def test_validate_audio_format_unsupported(self, tmp_path):
        """Test validation of unsupported format."""
        from utils.audio_utils import validate_audio_format
        
        test_file = tmp_path / "test.xyz"
        test_file.write_text("dummy")
        
        is_valid, error = validate_audio_format(str(test_file))
        assert not is_valid
        assert "unsupported" in error.lower()
    
    def test_validate_audio_format_valid(self, tmp_path):
        """Test validation of valid format."""
        from utils.audio_utils import validate_audio_format
        
        test_file = tmp_path / "test.wav"
        test_file.write_bytes(b"dummy")
        
        is_valid, error = validate_audio_format(str(test_file))
        assert is_valid
        assert error is None
    
    def test_create_audio_chunk_generator(self):
        """Test audio chunk generator."""
        from utils.audio_utils import create_audio_chunk_generator
        
        # Create 10000 bytes of audio data
        audio_data = bytes(range(256)) * 40  # 10240 bytes
        
        chunks = list(create_audio_chunk_generator(audio_data, chunk_size=3200))
        
        # Should produce 4 chunks (10240 / 3200 = 3.2, rounded up to 4)
        assert len(chunks) == 4
        assert len(chunks[0]) == 3200
        assert len(chunks[1]) == 3200
        assert len(chunks[2]) == 3200
        assert len(chunks[3]) == 640  # Remaining bytes


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

