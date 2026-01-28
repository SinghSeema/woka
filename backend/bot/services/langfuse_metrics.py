"""LangfuseMetrics processor for turn-by-turn observability.

This processor observes frames as they flow through the pipeline and creates
turn-level traces in Langfuse and OpenTelemetry without blocking the pipeline.
"""

import sys
import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Dict
from datetime import datetime
import uuid
import random
import time

backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.core.logging import get_logger
from app.core.observability import (
    get_langfuse,
    get_tracer,
    get_or_create_session_trace,
    record_llm_ttft_event,
)

try:
    from pipecat.processors.frame_processor import FrameProcessor, FrameDirection
except ImportError:  # pragma: no cover - should exist in runtime
    FrameProcessor = object  # type: ignore[assignment]
    FrameDirection = object  # type: ignore[assignment]

try:
    from pipecat.frames.frames import (
        LLMMessagesFrame,
        LLMFullResponseStartFrame,
        LLMTextFrame,
        OpenAILLMContextFrame,
        LLMContextFrame,
        Frame,
    )
except ImportError:  # pragma: no cover - allow partial availability
    LLMMessagesFrame = None
    LLMFullResponseStartFrame = None
    LLMTextFrame = None
    OpenAILLMContextFrame = None
    LLMContextFrame = None
    Frame = object  # type: ignore[assignment]

logger = get_logger(__name__)


class LlmRequestStartProcessor(FrameProcessor):
    """Marks the start time of an LLM request (pre-LLM)."""

    def __init__(self, shared_state: dict, **kwargs):
        super().__init__(**kwargs)
        self.shared_state = shared_state

    async def process_frame(self, frame: "Frame", direction: "FrameDirection"):
        """Marks the start time of an LLM request (pre-LLM)."""
        await super().process_frame(frame, direction)

        # Only track downstream frames
        if direction != FrameDirection.DOWNSTREAM:
            await self.push_frame(frame)
            return

        # Robust frame type detection using class names as strings
        frame_type = frame.__class__.__name__
        
        if frame_type in [
            "OpenAILLMContextFrame", 
            "LLMContextFrame", 
            "LLMMessagesFrame"
        ]:
            # Mark LLM request start
            self.shared_state["llm_request_start_ts"] = time.monotonic()
            self.shared_state["llm_ttft_recorded"] = False
            logger.info(f"🚀 LLM request started (trigger: {frame_type})")

        await self.push_frame(frame)


class LangfuseMetrics(FrameProcessor):
    """Processor that creates turn-by-turn observability without blocking pipeline.
    
    Observes LLMMessagesFrame to detect user/assistant turns and creates:
    - Langfuse traces/spans for each turn
    - OpenTelemetry spans for turn-level tracing
    - Non-blocking async operations to avoid pipeline slowdown
    """
    
    def __init__(
        self,
        user_name: str,
        room_name: str,
        environment: str = "prod",
        eval_run_id: Optional[str] = None,
        shared_state: Optional[dict] = None,
        **kwargs,
    ):
        """Initialize LangfuseMetrics processor.
        
        Args:
            user_name: User's name for tagging
            room_name: Room/session identifier
            environment: Environment tag ('prod', 'eval', 'dev')
            eval_run_id: Optional eval run ID for eval tagging
        """
        super().__init__(**kwargs)
        self.user_name = user_name
        self.room_name = room_name
        self.environment = environment
        self.eval_run_id = eval_run_id
        
        # Turn tracking state
        self.active_turns: Dict[str, Dict] = {}  # turn_id -> turn metadata
        self.user_message_timestamps: Dict[str, datetime] = {}  # message_hash -> timestamp
        
        # Observability clients
        self.langfuse = get_langfuse()
        self.tracer = get_tracer()

        # Session-level trace/span so all turns & events are grouped together in Langfuse.
        # We rely on the shared helper so that other observability hooks can attach
        # events to the same root trace.
        self.session_trace = get_or_create_session_trace(
            user_name=self.user_name,
            room_name=self.room_name,
            environment=self.environment,
            eval_run_id=self.eval_run_id,
        )

        # Turn metrics gating & sampling
        self.turn_metrics_enabled = bool(getattr(settings, "LANGFUSE_TURN_METRICS_ENABLED", True))
        if getattr(settings, "is_production", False) and not getattr(
            settings, "LANGFUSE_TURN_METRICS_IN_PROD", True
        ):
            self.turn_metrics_enabled = False
        self.turn_sample_rate = float(getattr(settings, "LANGFUSE_TURN_SAMPLE_RATE", 1.0))

        # LLM TTFT tracking (model-only)
        if shared_state is None:
            shared_state = {}
        self.shared_state = shared_state
        self.shared_state.setdefault("llm_request_start_ts", None)
        self.shared_state.setdefault("llm_ttft_recorded", False)
        
        logger.debug(
            f"LangfuseMetrics initialized: user={user_name}, room={room_name}, "
            f"env={environment}, eval_run={eval_run_id}"
        )
    
    async def process_frame(self, frame: "Frame", direction: "FrameDirection"):
        """Process frame and create observability traces (non-blocking).
        
        Args:
            frame: Frame to process
            direction: Frame direction
            
        Returns:
            Frame (passes through unchanged)
        """
        # Let the base class handle system frames (StartFrame, CancelFrame, etc.)
        await super().process_frame(frame, direction)

        # Only track downstream frames for metrics
        if direction != FrameDirection.DOWNSTREAM:
            await self.push_frame(frame)
            return

        # Robust frame type detection using class names as strings
        frame_type = frame.__class__.__name__

        # Identify when LLM starts responding (first token or response start)
        # Using partial matches to be robust across Pipecat versions
        is_llm_start = any(marker in frame_type for marker in [
            "FullResponseStart",
            "ResponseStart",
            "LLMText",
            "TextFrame"
        ])

        if (
            is_llm_start
            and self.shared_state.get("llm_request_start_ts") is not None
            and not self.shared_state.get("llm_ttft_recorded")
        ):
            # Double-check protection for race conditions between frames
            if self.shared_state.get("llm_ttft_recorded"):
                await self.push_frame(frame)
                return

            # Double check for TextFrame: only count if it has content
            has_content = True
            if "TextFrame" in frame_type:
                content = getattr(frame, "text", "") or getattr(frame, "content", "")
                has_content = bool(content and content.strip())

            if has_content:
                # Set flag IMMEDIATELY to prevent double logging
                self.shared_state["llm_ttft_recorded"] = True
                
                llm_ttft_ms = (
                    time.monotonic() - self.shared_state["llm_request_start_ts"]
                ) * 1000
                
                # Model-only TTFT is crucial for debugging infrastructure vs model latency
                logger.info(f"⚡ LLM TTFT: {llm_ttft_ms:.0f}ms (Model: {getattr(settings, 'LLM_MODEL', 'unknown')})")
                
                # Record in Langfuse if enabled
                record_llm_ttft_event(
                    user_name=self.user_name,
                    room_name=self.room_name,
                    ttft_ms=llm_ttft_ms,
                    model_name=getattr(settings, "LLM_MODEL", None),
                )

        # Process LLMMessagesFrame (user/assistant messages) for turn tracking
        if frame_type == "LLMMessagesFrame":
            # Process asynchronously without blocking pipeline
            asyncio.create_task(self._process_messages_frame(frame))
        
        # Also detect turns from LLMContext frames (input to LLM)
        elif "LLMContextFrame" in frame_type or "OpenAILLMContextFrame" in frame_type:
            # If it's an input frame going to LLM, we can use it to start/update the turn
            asyncio.create_task(self._process_context_frame(frame))

        # Always forward the frame downstream
        await self.push_frame(frame)

    async def _process_context_frame(self, frame):
        """Process context frames as turn signals (no logging here to avoid duplicates)."""
        try:
            messages = getattr(frame, "messages", [])
            if not messages and hasattr(frame, "context"):
                messages = getattr(frame.context, "messages", [])
            
            if messages:
                # Last message is usually the user prompt in this frame
                last_msg = messages[-1]
                role = last_msg.get("role") if isinstance(last_msg, dict) else getattr(last_msg, "role", "")
                content = last_msg.get("content") if isinstance(last_msg, dict) else getattr(last_msg, "content", "")
                
                if role == "user":
                    await self._handle_user_message(content)
        except Exception as e:
            logger.debug(f"Error processing context frame: {e}")
    
    async def _process_messages_frame(self, frame):
        """Process LLMMessagesFrame and create traces (async, non-blocking)."""
        try:
            # Extract messages from frame
            messages = []
            if hasattr(frame, 'messages'):
                messages = frame.messages
            elif isinstance(frame, dict) and 'messages' in frame:
                messages = frame['messages']
            
            if not messages:
                return
            
            # Process each message in the frame
            for msg in messages:
                if isinstance(msg, dict):
                    role = msg.get("role", "")
                    content = msg.get("content", "")
                else:
                    # Handle message objects with attributes
                    role = getattr(msg, "role", "")
                    content = getattr(msg, "content", "")
                
                if role == "user" and content:
                    await self._handle_user_message(content)
                elif role == "assistant" and content:
                    await self._handle_assistant_message(content)
                    
        except Exception as e:
            # Never block pipeline on observability errors
            logger.debug(f"Error in LangfuseMetrics (non-critical): {e}")
    
    async def _handle_user_message(self, content: str):
        """Handle user message - start turn tracking."""
        if not content or not content.strip():
            return

        if not self.turn_metrics_enabled:
            return

        if self.turn_sample_rate <= 0.0:
            return

        if self.turn_sample_rate < 1.0 and random.random() > self.turn_sample_rate:
            return
        
        # Create unique turn ID
        turn_id = str(uuid.uuid4())
        message_hash = hash(content)
        timestamp = datetime.now()
        
        # Store turn metadata
        self.active_turns[turn_id] = {
            "user_message": content,
            "user_timestamp": timestamp,
            "turn_id": turn_id,
            "langfuse_trace": None,
            "otel_span": None,
        }
        self.user_message_timestamps[message_hash] = timestamp
        
        # Start OpenTelemetry span (if enabled)
        if self.tracer:
            try:
                span = self.tracer.start_span(
                    "llm_turn",
                    attributes={
                        "user_name": self.user_name,
                        "room_name": self.room_name,
                        "turn_id": turn_id,
                        "environment": self.environment,
                        "user_message": content[:200],  # Truncate for safety
                    }
                )
                if self.eval_run_id:
                    span.set_attribute("eval_run_id", self.eval_run_id)
                self.active_turns[turn_id]["otel_span"] = span
            except Exception as e:
                logger.debug(f"Error creating OTel span: {e}")
        
        # Start Langfuse span (if enabled)
        if self.langfuse:
            try:
                span = None

                # If we have a session root trace/span that supports child spans, prefer that.
                if self.session_trace is not None:
                    # Newer SDKs may expose `.span(...)` on trace objects.
                    if hasattr(self.session_trace, "span"):
                        span = self.session_trace.span(
                            name="llm_turn",
                            input=content[:500],
                            metadata={
                                "turn_id": turn_id,
                                "environment": self.environment,
                                "room_name": self.room_name,
                                "user_name": self.user_name,
                            },
                        )
                    # Older-style API: `.start_span(...)` on the trace/span object.
                    elif hasattr(self.session_trace, "start_span"):
                        span = self.session_trace.start_span(
                            name="llm_turn",
                            input=content[:500],
                            metadata={
                                "turn_id": turn_id,
                                "environment": self.environment,
                                "room_name": self.room_name,
                                "user_name": self.user_name,
                            },
                        )

                # Fallback: start span directly from client (older SDKs or if trace creation failed).
                if span is None and hasattr(self.langfuse, "start_span"):
                    span = self.langfuse.start_span(
                        name="llm_turn",
                        input=content[:500],
                        metadata={
                            "turn_id": turn_id,
                            "environment": self.environment,
                            "room_name": self.room_name,
                            "user_name": self.user_name,
                        },
                    )

                if span is not None and self.eval_run_id:
                    try:
                        span.update(metadata={"eval_run_id": self.eval_run_id})
                    except Exception:
                        # Be tolerant of SDKs without update/metadata APIs.
                        pass

                if span is not None:
                    self.active_turns[turn_id]["langfuse_span"] = span
            except Exception as e:
                logger.debug(f"Error creating Langfuse span: {e}")
    
    async def _handle_assistant_message(self, content: str):
        """Handle assistant message - complete turn tracking."""
        if not content or not content.strip():
            return
        
        # Find the most recent active turn (simple: use last turn)
        if not self.active_turns:
            return
        
        # Get the most recent turn (could be improved with better matching)
        turn_id = max(self.active_turns.keys(), key=lambda k: self.active_turns[k]["user_timestamp"])
        turn_meta = self.active_turns[turn_id]
        user_timestamp = turn_meta["user_timestamp"]
        
        # Calculate TTFT
        assistant_timestamp = datetime.now()
        ttft_ms = (assistant_timestamp - user_timestamp).total_seconds() * 1000
        
        # Complete OpenTelemetry span
        otel_span = turn_meta.get("otel_span")
        if otel_span:
            try:
                otel_span.set_attribute("ttft_ms", ttft_ms)
                otel_span.set_attribute("assistant_message_length", len(content))
                otel_span.end()
            except Exception as e:
                logger.debug(f"Error ending OTel span: {e}")
        
        # Complete Langfuse trace
        langfuse_span = turn_meta.get("langfuse_span")
        if langfuse_span:
            try:
                # Update and end span with response info
                langfuse_span.update(
                    output=content[:500],
                    metadata={
                        "ttft_ms": ttft_ms,
                        "message_length": len(content),
                        "completed": True,
                    },
                )
                langfuse_span.end()
            except Exception as e:
                logger.debug(f"Error completing Langfuse span: {e}")
        
        # Cleanup
        del self.active_turns[turn_id]
    
    def get_turn_metrics(self) -> Dict:
        """Get current turn metrics (for debugging/monitoring).
        
        Returns:
            Dictionary with active turns and metrics
        """
        return {
            "active_turns": len(self.active_turns),
            "environment": self.environment,
            "eval_run_id": self.eval_run_id,
        }

