"""Backchannel filter — drops single-word acknowledgment frames before they reach the LLM.

Without this, words like "ok", "yeah", "mm-hmm" get added to the conversation
context and trigger a new LLM response, causing an awkward short-silence/restart loop.

The filter acts regardless of whether the bot is currently speaking, which is the
scenario the MinWordsInterruptionStrategy cannot handle (it only applies mid-speech).
"""

from pipecat.frames.frames import Frame, TranscriptionFrame
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection
from app.core.logging import get_logger

logger = get_logger(__name__)

# Words that are conversational acknowledgments and should never start an LLM turn.
# Keep this list tight — over-filtering kills real short commands ("stop", "wait", "help").
_BACKCHANNEL = {
    "ok", "okay", "yeah", "yep", "yup", "yes", "nope", "no",
    "mm", "hmm", "mhm", "mmm", "uh", "uhh", "uh-huh",
    "right", "sure", "got", "gotcha", "alright",
}


def _is_backchannel(text: str) -> bool:
    """Return True if every meaningful token in *text* is a backchannel word."""
    # Strip punctuation and normalise
    cleaned = text.lower().strip(" .,!?")
    tokens = [t.strip(".,!?") for t in cleaned.split() if t.strip(".,!?")]
    if not tokens:
        return True
    return all(t in _BACKCHANNEL for t in tokens)


class BackchannelFilter(FrameProcessor):
    """Drop TranscriptionFrames that contain only backchannel acknowledgment words."""

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        # super() handles StartFrame internally (sets __started = True) but does NOT push.
        # push_frame() requires __started = True, so super() must be called first.
        await super().process_frame(frame, direction)

        # After super(), drop backchannel transcriptions; forward everything else.
        if isinstance(frame, TranscriptionFrame) and _is_backchannel(frame.text):
            logger.debug(f"BackchannelFilter: dropped '{frame.text.strip()}'")
            return

        await self.push_frame(frame, direction)
