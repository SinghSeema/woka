"""Token tracking processor for LLM responses."""

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Optional
import time

backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.core.logging import get_logger

if TYPE_CHECKING:
    from pipecat.frames.frames import Frame
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

logger = get_logger(__name__)


class TokenTrackerProcessor:
    """Processor that tracks token usage from LLM responses."""
    
    def __init__(self, performance_monitor=None, user_name: str = "", room_name: str = ""):
        """Initialize token tracker.
        
        Args:
            performance_monitor: PerformanceMonitor instance
            user_name: User's name for tracking
            room_name: Room name for tracking
        """
        self.performance_monitor = performance_monitor
        self.user_name = user_name
        self.room_name = room_name
        self.request_start_time = None
        
    async def process_frame(self, frame: "Frame", direction: "FrameDirection"):
        """Process frames to extract token usage.
        
        Args:
            frame: Frame to process
            direction: Frame direction
        """
        # Track LLM request start
        if hasattr(frame, 'type') and 'llm' in str(frame.type).lower():
            self.request_start_time = time.time()
        
        # Try to extract token usage from LLM response frames
        try:
            # Check if frame has token usage information
            if hasattr(frame, 'usage') or hasattr(frame, 'token_usage'):
                usage = getattr(frame, 'usage', None) or getattr(frame, 'token_usage', None)
                if usage:
                    input_tokens = getattr(usage, 'prompt_tokens', None) or getattr(usage, 'input_tokens', None)
                    output_tokens = getattr(usage, 'completion_tokens', None) or getattr(usage, 'output_tokens', None)
                    
                    if input_tokens is not None or output_tokens is not None:
                        duration_ms = 0
                        if self.request_start_time:
                            duration_ms = (time.time() - self.request_start_time) * 1000
                            self.request_start_time = None
                        
                        if self.performance_monitor:
                            self.performance_monitor.record_request(
                                user_name=self.user_name,
                                room_name=self.room_name,
                                request_type='llm',
                                duration_ms=duration_ms,
                                input_tokens=input_tokens or 0,
                                output_tokens=output_tokens or 0,
                                success=True
                            )
                            logger.debug(
                                f"📊 Token usage tracked: "
                                f"input={input_tokens or 0}, output={output_tokens or 0}"
                            )
            
            # Alternative: Check frame data/metadata for token info
            if hasattr(frame, 'data'):
                frame_data = frame.data
                if isinstance(frame_data, dict):
                    usage = frame_data.get('usage') or frame_data.get('token_usage')
                    if usage:
                        input_tokens = usage.get('prompt_tokens') or usage.get('input_tokens')
                        output_tokens = usage.get('completion_tokens') or usage.get('output_tokens')
                        
                        if input_tokens is not None or output_tokens is not None:
                            duration_ms = 0
                            if self.request_start_time:
                                duration_ms = (time.time() - self.request_start_time) * 1000
                                self.request_start_time = None
                            
                            if self.performance_monitor:
                                self.performance_monitor.record_request(
                                    user_name=self.user_name,
                                    room_name=self.room_name,
                                    request_type='llm',
                                    duration_ms=duration_ms,
                                    input_tokens=input_tokens or 0,
                                    output_tokens=output_tokens or 0,
                                    success=True
                                )
                                logger.debug(
                                    f"📊 Token usage tracked (from data): "
                                    f"input={input_tokens or 0}, output={output_tokens or 0}"
                                )
        
        except Exception as e:
            logger.debug(f"Error extracting token usage from frame: {e}")
        
        # Pass frame through
        return frame

