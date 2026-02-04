"""STT Intent Processor - Early intent detection on speech_final frames.

This processor intercepts STT TextFrames and triggers intent detection
only when speech_final is true (user has finished speaking), avoiding
processing of interim results for better performance and accuracy.
"""

import sys
import asyncio
from pathlib import Path
from typing import Optional, Dict
from dataclasses import dataclass
import time

backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.core.logging import get_logger
from bot.services.intent_detector import detect_past_reference_intent, PastReferenceIntent

try:
    from pipecat.frames.frames import Frame, TextFrame
    from pipecat.processors.frame_processor import FrameProcessor, FrameDirection
except ImportError:
    Frame = object
    TextFrame = object
    FrameProcessor = object
    FrameDirection = object

logger = get_logger(__name__)


@dataclass
class IntentCacheEntry:
    """Cached intent detection result."""
    intent: PastReferenceIntent
    timestamp: float
    text: str


class STTIntentProcessor(FrameProcessor):
    """Processor that detects intent early on speech_final frames.
    
    This runs BEFORE the context aggregator, allowing intent detection
    to happen in parallel with message collection. Only processes
    complete sentences (speech_final: true) to avoid wasting resources
    on interim results.
    """
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Cache for intent results (keyed by text hash)
        self._intent_cache: Dict[int, IntentCacheEntry] = {}
        # Track processed texts to avoid duplicates
        self._processed_texts = set()
        # Cache expiration time (5 seconds)
        self._cache_ttl = 5.0
        
        logger.info(
            f"🔧 [STT-INTENT] STTIntentProcessor initialized: "
            f"ENABLE_DYNAMIC_CONTEXT={settings.ENABLE_DYNAMIC_CONTEXT}, "
            f"ENABLE_SEMANTIC_SEARCH={settings.ENABLE_SEMANTIC_SEARCH}"
        )
    
    def _check_speech_final(self, frame: Frame) -> bool:
        """Check if frame represents a speech_final event.
        
        Deepgram sends speech_final: true when endpoint detection
        triggers (user stopped speaking). This is the best time to
        trigger intent detection.
        
        Args:
            frame: Frame to check
            
        Returns:
            True if this is a speech_final frame, False otherwise
        """
        # Try multiple ways to access speech_final flag
        # Pipecat may expose it differently depending on version
        
        frame_type = type(frame).__name__
        
        # Method 1: Direct attribute
        if hasattr(frame, 'speech_final'):
            result = bool(frame.speech_final)
            logger.debug(
                f"🔬 [STT-INTENT] Found 'speech_final' attribute on {frame_type}: {frame.speech_final} -> {result}"
            )
            return result
        
        # Method 2: is_final attribute (some versions use this)
        if hasattr(frame, 'is_final'):
            result = bool(frame.is_final)
            logger.debug(
                f"🔬 [STT-INTENT] Found 'is_final' attribute on {frame_type}: {frame.is_final} -> {result}"
            )
            return result
        
        # Method 3: Metadata dictionary
        if hasattr(frame, 'metadata') and isinstance(frame.metadata, dict):
            speech_final_meta = frame.metadata.get('speech_final', False)
            is_final_meta = frame.metadata.get('is_final', False)
            result = bool(speech_final_meta or is_final_meta)
            logger.debug(
                f"🔬 [STT-INTENT] Found in metadata on {frame_type}: "
                f"speech_final={speech_final_meta}, is_final={is_final_meta} -> {result}"
            )
            return result
        
        # Method 4: Check for Deepgram-specific attributes
        if hasattr(frame, 'data') and isinstance(frame.data, dict):
            speech_final_data = frame.data.get('speech_final', False)
            is_final_data = frame.data.get('is_final', False)
            result = bool(speech_final_data or is_final_data)
            logger.debug(
                f"🔬 [STT-INTENT] Found in data dict on {frame_type}: "
                f"speech_final={speech_final_data}, is_final={is_final_data} -> {result}"
            )
            return result
        
        # Method 5: Check frame type name for hints
        if 'Final' in frame_type or 'SpeechFinal' in frame_type:
            logger.debug(
                f"🔬 [STT-INTENT] Frame type name suggests finality: {frame_type} -> True"
            )
            return True
        
        # Default: If we can't determine, assume it's final
        # (Better to process than miss it)
        # But log a warning so we can investigate
        frame_attrs = [attr for attr in dir(frame) if not attr.startswith('_')]
        logger.debug(
            f"⚠️  [STT-INTENT] Cannot determine speech_final status for frame type {frame_type}, "
            f"assuming final. Frame attributes: {frame_attrs}"
        )
        return True  # Conservative: assume final if we can't tell
    
    async def _detect_intent_async(self, text: str) -> None:
        """Async intent detection - runs in background.
        
        This is non-blocking and runs in parallel with context aggregation.
        Results are cached for PastContextProcessor to use.
        
        Args:
            text: User message text to analyze
        """
        try:
            # Normalize text for consistent hashing
            normalized_text = text.strip().lower()
            text_hash = hash(normalized_text)
            
            # Skip if already processed
            if text_hash in self._processed_texts:
                logger.debug(f"⏭️  [STT-INTENT] Text already processed, skipping")
                return
            
            self._processed_texts.add(text_hash)
            
            # Only process if dynamic context is enabled
            if not settings.ENABLE_DYNAMIC_CONTEXT:
                logger.debug(f"⏭️  [STT-INTENT] ENABLE_DYNAMIC_CONTEXT disabled, skipping")
                return
            
            logger.debug(
                f"🔍 [STT-INTENT] Starting async intent detection for: '{text[:50]}...'"
            )
            
            # Detect intent (async, may take 10-50ms)
            # Use original text (not normalized) for intent detection to preserve case/punctuation
            intent = await detect_past_reference_intent(text)
            
            # Cache the result using normalized hash for lookup
            # Store original (stripped) text for fuzzy matching
            self._intent_cache[text_hash] = IntentCacheEntry(
                intent=intent,
                timestamp=time.time(),
                text=text.strip()  # Store original (stripped) text for fuzzy matching
            )
            
            if intent.has_intent:
                logger.info(
                    f"✅ [STT-INTENT] Early detection completed and cached: "
                    f"intent_type={intent.intent_type}, confidence={intent.confidence:.3f}, "
                    f"cache_size={len(self._intent_cache)}, text_hash={text_hash}"
                )
            else:
                logger.debug(
                    f"⏭️  [STT-INTENT] No intent detected (similarity={intent.confidence:.3f}), "
                    f"but cached anyway. cache_size={len(self._intent_cache)}, text_hash={text_hash}"
                )
                
        except Exception as e:
            logger.error(
                f"❌ [STT-INTENT] Error in async intent detection: {e}",
                exc_info=True
            )
    
    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process frame and trigger intent detection on speech_final.
        
        This is NON-BLOCKING - frame passes through immediately.
        Intent detection runs asynchronously in background.
        """
        await super().process_frame(frame, direction)
        
        frame_type = type(frame).__name__
        is_text_frame = isinstance(frame, TextFrame)
        is_upstream = direction == FrameDirection.UPSTREAM
        
        # Log first few frames to understand what we're receiving
        if not hasattr(self, '_frame_log_count'):
            self._frame_log_count = 0
        if self._frame_log_count < 10:
            logger.info(
                f"📥 [STT-INTENT] Frame received: type={frame_type}, "
                f"is_text_frame={is_text_frame}, direction={direction}, "
                f"is_upstream={is_upstream}, "
                f"has_text={hasattr(frame, 'text')}, has_data={hasattr(frame, 'data')}"
            )
            self._frame_log_count += 1
        
        # Only process TextFrames from STT (upstream direction)
        # These come from Deepgram STT service
        if is_text_frame and is_upstream:
            logger.debug(
                f"📥 [STT-INTENT] Received TextFrame (UPSTREAM): type={frame_type}, "
                f"has_text={hasattr(frame, 'text')}, has_data={hasattr(frame, 'data')}"
            )
            # Check if this is a speech_final frame
            is_speech_final = self._check_speech_final(frame)
            
            if is_speech_final:
                # Get text from frame
                text = getattr(frame, 'text', '') or getattr(frame, 'data', '')
                if isinstance(text, dict):
                    text = text.get('text', '') or text.get('transcript', '')
                
                if text and text.strip():
                    # Store original text (stripped) for intent detection
                    # Normalization happens inside _detect_intent_async for cache key
                    original_text = text.strip()
                    # Trigger async intent detection (NON-BLOCKING)
                    # Don't await - let it run in background
                    asyncio.create_task(self._detect_intent_async(original_text))
                    logger.info(
                        f"🚀 [STT-INTENT] Triggered async intent detection for speech_final: "
                        f"'{original_text[:50]}...'"
                    )
                else:
                    logger.debug(
                        f"⏭️  [STT-INTENT] Speech_final frame has no text content "
                        f"(text={repr(text)})"
                    )
            else:
                # Interim result - skip processing
                logger.debug(
                    f"⏭️  [STT-INTENT] Skipping interim result (is_speech_final=False)"
                )
        else:
            # Log when we receive non-TextFrame or wrong direction (for debugging)
            if isinstance(frame, TextFrame):
                logger.debug(
                    f"⏭️  [STT-INTENT] TextFrame received but direction={direction} "
                    f"(expected UPSTREAM), skipping. Frame type: {frame_type}"
                )
            elif direction == FrameDirection.UPSTREAM:
                logger.debug(
                    f"⏭️  [STT-INTENT] Non-TextFrame received in UPSTREAM direction: "
                    f"type={frame_type}, skipping"
                )
        
        # Pass frame through immediately (NO DELAY)
        await self.push_frame(frame, direction)
    
    def get_cached_intent(self, text: str) -> Optional[PastReferenceIntent]:
        """Get cached intent result for text.
        
        Called by PastContextProcessor to retrieve pre-computed intent.
        
        Args:
            text: User message text
            
        Returns:
            PastReferenceIntent if cached, None otherwise
        """
        # Normalize text for matching (strip whitespace, lowercase for comparison)
        normalized_text = text.strip().lower()
        text_hash = hash(normalized_text)
        
        # Try exact match first
        entry = self._intent_cache.get(text_hash)
        
        # If no exact match, try fuzzy matching by checking all cache entries
        # (in case text formatting differs slightly)
        if not entry:
            logger.debug(
                f"🔍 [STT-INTENT] No exact cache match for '{text[:50]}...', "
                f"checking {len(self._intent_cache)} cached entries..."
            )
            # Try to find a match by comparing normalized text
            for cached_hash, cached_entry in self._intent_cache.items():
                cached_normalized = cached_entry.text.strip().lower()
                # Check if texts are similar (allowing for minor differences)
                if normalized_text == cached_normalized or \
                   normalized_text in cached_normalized or \
                   cached_normalized in normalized_text:
                    entry = cached_entry
                    logger.debug(
                        f"✅ [STT-INTENT] Found fuzzy match: "
                        f"query='{text[:30]}...' matches cached='{cached_entry.text[:30]}...'"
                    )
                    break
        
        if entry:
            # Check if cache entry is still valid (within TTL)
            if time.time() - entry.timestamp < self._cache_ttl:
                logger.info(
                    f"✅ [STT-INTENT] Cache hit for text: '{text[:50]}...' "
                    f"(cached text: '{entry.text[:50]}...')"
                )
                return entry.intent
            else:
                # Cache expired, remove it
                del self._intent_cache[text_hash]
                logger.debug(f"⏭️  [STT-INTENT] Cache expired for text")
        else:
            logger.debug(
                f"⏭️  [STT-INTENT] No cache match for '{text[:50]}...' "
                f"(cache has {len(self._intent_cache)} entries)"
            )
        
        return None
    
    def get_cache_size(self) -> int:
        """Get current cache size (for debugging/logging)."""
        return len(self._intent_cache)
    
    def clear_cache(self):
        """Clear intent cache (useful for testing or memory management)."""
        self._intent_cache.clear()
        self._processed_texts.clear()
        logger.debug("🧹 [STT-INTENT] Cache cleared")

