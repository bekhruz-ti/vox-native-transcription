"""
Guard against the injection gate regression.

Transcribed text used to be typed only when UI Automation classified the
focused element as an EditControl, so Electron/web text areas (which report
GroupControl or PaneControl) silently got nothing. Injection must now happen
regardless of what has focus.

Run: python tests/test_injection_not_gated.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.session import RecordingSession
from src.providers.base import (
    RealtimeTranscriptionOutput,
    TranscriptionOutputType,
    TranscriptionStatus,
)


class FakeInjector:
    def __init__(self):
        self.injected: list[str] = []

    def inject(self, text: str) -> None:
        self.injected.append(text)

    def reset_incremental(self) -> None:
        pass


def make_session(injector: FakeInjector) -> RecordingSession:
    return RecordingSession(recorder=None, provider=None, text_injector=injector)


def test_cumulative_complete_is_injected() -> None:
    injector = FakeInjector()
    make_session(injector)._on_text_update(
        RealtimeTranscriptionOutput(
            type=TranscriptionOutputType.CUMULATIVE,
            chunks=["hello world"],
            latest_transcription="hello world",
            status=TranscriptionStatus.COMPLETE,
            final_transcription="hello world",
        )
    )
    assert injector.injected == ["hello world"], injector.injected


def test_cumulative_in_progress_is_not_injected() -> None:
    """Partial cumulative text must wait, or the field fills with duplicates."""
    injector = FakeInjector()
    make_session(injector)._on_text_update(
        RealtimeTranscriptionOutput(
            type=TranscriptionOutputType.CUMULATIVE,
            chunks=["hello"],
            latest_transcription="hello",
            status=TranscriptionStatus.IN_PROGRESS,
        )
    )
    assert injector.injected == [], injector.injected


def test_incremental_chunk_is_injected() -> None:
    injector = FakeInjector()
    make_session(injector)._on_text_update(
        RealtimeTranscriptionOutput(
            type=TranscriptionOutputType.INCREMENTAL,
            chunks=["hello", " world"],
            latest_transcription="hello world",
            status=TranscriptionStatus.IN_PROGRESS,
        )
    )
    assert injector.injected == [" world"], injector.injected


def main() -> int:
    test_cumulative_complete_is_injected()
    test_cumulative_in_progress_is_not_injected()
    test_incremental_chunk_is_injected()
    print("OK: transcribed text is injected regardless of the focused control type")
    return 0


if __name__ == "__main__":
    sys.exit(main())
