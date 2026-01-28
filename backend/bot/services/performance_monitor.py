"""Performance monitoring and metrics collection."""

import sys
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import deque

backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.core.logging import get_logger
from bot.services.context_manager import estimate_tokens

logger = get_logger(__name__)


@dataclass
class RequestMetrics:
    """Metrics for a single request."""
    timestamp: datetime
    request_type: str  # 'llm', 'embedding', 'database', etc.
    duration_ms: float
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    success: bool = True
    error: Optional[str] = None


@dataclass
class SessionMetrics:
    """Metrics for a session."""
    user_name: str
    session_start: datetime
    total_requests: int = 0
    total_tokens_input: int = 0
    total_tokens_output: int = 0
    total_cost: float = 0.0
    request_history: deque = field(default_factory=lambda: deque(maxlen=100))
    errors: List[str] = field(default_factory=list)


class PerformanceMonitor:
    """Monitor performance metrics for the bot."""
    
    def __init__(self):
        """Initialize performance monitor."""
        self.sessions: Dict[str, SessionMetrics] = {}
        self.enabled = getattr(settings, 'ENABLE_PERFORMANCE_MONITORING', True)
        
        if self.enabled:
            logger.info("✅ Performance monitoring enabled")
        else:
            logger.debug("Performance monitoring disabled")
    
    def start_session(self, user_name: str, room_name: str) -> None:
        """Start tracking metrics for a session.
        
        Args:
            user_name: User's name
            room_name: Room/session identifier
        """
        if not self.enabled:
            return
        
        session_key = f"{user_name}:{room_name}"
        self.sessions[session_key] = SessionMetrics(
            user_name=user_name,
            session_start=datetime.now()
        )
        logger.debug(f"Started performance monitoring for session: {session_key}")
    
    def record_request(
        self,
        user_name: str,
        room_name: str,
        request_type: str,
        duration_ms: float,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        success: bool = True,
        error: Optional[str] = None
    ) -> None:
        """Record a request metric.
        
        Args:
            user_name: User's name
            room_name: Room/session identifier
            request_type: Type of request ('llm', 'embedding', 'database', etc.)
            duration_ms: Request duration in milliseconds
            input_tokens: Input tokens (if applicable)
            output_tokens: Output tokens (if applicable)
            success: Whether request succeeded
            error: Error message if failed
        """
        if not self.enabled:
            return
        
        session_key = f"{user_name}:{room_name}"
        session = self.sessions.get(session_key)
        
        if not session:
            # Auto-create session if not exists
            self.start_session(user_name, room_name)
            session = self.sessions[session_key]
        
        metric = RequestMetrics(
            timestamp=datetime.now(),
            request_type=request_type,
            duration_ms=duration_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            success=success,
            error=error
        )
        
        session.request_history.append(metric)
        session.total_requests += 1
        
        if input_tokens:
            session.total_tokens_input += input_tokens
        if output_tokens:
            session.total_tokens_output += output_tokens
        
        if not success and error:
            session.errors.append(error)
        
        # Log slow requests
        if duration_ms > 2000:
            logger.warning(
                f"⚠️  Slow {request_type} request: {duration_ms:.0f}ms "
                f"(session: {session_key})"
            )
    
    def get_session_metrics(
        self,
        user_name: str,
        room_name: str
    ) -> Optional[Dict[str, Any]]:
        """Get metrics for a session.
        
        Args:
            user_name: User's name
            room_name: Room/session identifier
            
        Returns:
            Dictionary with session metrics or None
        """
        if not self.enabled:
            return None
        
        session_key = f"{user_name}:{room_name}"
        session = self.sessions.get(session_key)
        
        if not session:
            return None
        
        duration = (datetime.now() - session.session_start).total_seconds()
        
        # Calculate average response time
        avg_duration = 0.0
        if session.request_history:
            avg_duration = sum(
                m.duration_ms for m in session.request_history
            ) / len(session.request_history)
        
        return {
            "user_name": session.user_name,
            "session_duration_seconds": duration,
            "total_requests": session.total_requests,
            "total_tokens_input": session.total_tokens_input,
            "total_tokens_output": session.total_tokens_output,
            "total_tokens": session.total_tokens_input + session.total_tokens_output,
            "average_response_time_ms": avg_duration,
            "error_count": len(session.errors),
            "errors": session.errors[-5:]  # Last 5 errors
        }
    
    def log_session_summary(
        self,
        user_name: str,
        room_name: str
    ) -> None:
        """Log a summary of session metrics.
        
        Args:
            user_name: User's name
            room_name: Room/session identifier
        """
        if not self.enabled:
            return
        
        metrics = self.get_session_metrics(user_name, room_name)
        if not metrics:
            return
        
        logger.info("=" * 60)
        logger.info("📊 SESSION PERFORMANCE SUMMARY")
        logger.info(f"   User: {user_name}")
        logger.info(f"   Duration: {metrics['session_duration_seconds']:.1f}s")
        logger.info(f"   Total Requests: {metrics['total_requests']}")
        logger.info(f"   Total Tokens: {metrics['total_tokens']} (in: {metrics['total_tokens_input']}, out: {metrics['total_tokens_output']})")
        logger.info(f"   Avg Response Time: {metrics['average_response_time_ms']:.0f}ms")
        if metrics['error_count'] > 0:
            logger.warning(f"   Errors: {metrics['error_count']}")
        logger.info("=" * 60)
    
    def cleanup_session(self, user_name: str, room_name: str) -> None:
        """Clean up session metrics.
        
        Args:
            user_name: User's name
            room_name: Room/session identifier
        """
        session_key = f"{user_name}:{room_name}"
        if session_key in self.sessions:
            # Log summary before cleanup
            self.log_session_summary(user_name, room_name)
            del self.sessions[session_key]
            logger.debug(f"Cleaned up metrics for session: {session_key}")


# Global performance monitor instance
_performance_monitor = None


def get_performance_monitor() -> PerformanceMonitor:
    """Get or create global performance monitor instance.
    
    Returns:
        PerformanceMonitor instance
    """
    global _performance_monitor
    if _performance_monitor is None:
        _performance_monitor = PerformanceMonitor()
    return _performance_monitor

