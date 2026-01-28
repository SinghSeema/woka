"""Observability utilities: tracing (Jaeger/OTel) and Langfuse integration.

All dependencies are optional and gated by settings:
- Tracing: ENABLE_TRACING + opentelemetry installed
- Langfuse: ENABLE_LANGFUSE + langfuse installed
"""

from __future__ import annotations

from typing import Optional, Dict, Any, Tuple

import json
from datetime import datetime
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_tracer = None  # type: ignore[assignment]
_langfuse = None
_session_traces: Dict[Tuple[str, str], Any] = {}  # (user_name, room_name) -> Langfuse trace/span


def init_tracing(service_name: str = "woka-bot") -> None:
    """Initialize OpenTelemetry tracing with Jaeger/OTLP exporter (optional).

    - Uses OTLP gRPC to send traces to Jaeger/Tempo/OTel collector.
    - No-op if opentelemetry is not installed or ENABLE_TRACING is False.
    """
    global _tracer

    if not getattr(settings, "ENABLE_TRACING", False):
        logger.info("Tracing disabled (ENABLE_TRACING=False)")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except Exception as e:  # pragma: no cover - optional dependency
        logger.warning(
            "OpenTelemetry not available, tracing disabled. "
            "Install 'opentelemetry-sdk' and 'opentelemetry-exporter-otlp' to enable tracing. "
            f"Error: {e}"
        )
        return

    endpoint = getattr(settings, "JAEGER_ENDPOINT", None) or "http://localhost:4317"

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.namespace": "woka",
            "service.environment": settings.ENVIRONMENT,
        }
    )
    provider = TracerProvider(resource=resource)
    span_processor = BatchSpanProcessor(
        OTLPSpanExporter(endpoint=endpoint, insecure=True)
    )
    provider.add_span_processor(span_processor)
    trace.set_tracer_provider(provider)

    _tracer = trace.get_tracer(service_name)
    logger.info(f"Tracing initialized (endpoint={endpoint})")


def get_tracer():
    """Return OpenTelemetry tracer if initialized, else None."""
    return _tracer


def init_langfuse() -> None:
    """Initialize Langfuse client (optional).

    Requires:
    - ENABLE_LANGFUSE=True
    - LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY
    - langfuse package installed
    """
    global _langfuse

    if not getattr(settings, "ENABLE_LANGFUSE", False):
        logger.info("Langfuse disabled (ENABLE_LANGFUSE=False)")
        return

    if _langfuse is not None:
        return

    public_key = getattr(settings, "LANGFUSE_PUBLIC_KEY", None)
    secret_key = getattr(settings, "LANGFUSE_SECRET_KEY", None)
    host = getattr(settings, "LANGFUSE_HOST", "https://cloud.langfuse.com")

    if not public_key or not secret_key:
        logger.warning(
            "Langfuse enabled but LANGFUSE_PUBLIC_KEY/SECRET_KEY not set. "
            "Langfuse tracing will be disabled."
        )
        return

    try:
        from langfuse import Langfuse  # type: ignore[import]
    except Exception as e:  # pragma: no cover - optional dependency
        logger.warning(
            "langfuse package not installed, Langfuse integration disabled. "
            "Install 'langfuse' to enable. "
            f"Error: {e}"
        )
        return

    # Note: older versions of the Langfuse Python SDK do not support the
    # `sdk_integration` argument. To stay compatible, we only pass the
    # parameters that are guaranteed to exist.
    _langfuse = Langfuse(
        public_key=public_key,
        secret_key=secret_key,
        host=host,
        debug=False,
    )
    logger.info("Langfuse client initialized")


def get_langfuse():
    """Return Langfuse client if initialized, else None."""
    return _langfuse


def get_or_create_session_trace(
    *,
    user_name: str,
    room_name: str,
    environment: Optional[str] = None,
    eval_run_id: Optional[str] = None,
) -> Optional[Any]:
    """Get or create a Langfuse session trace/span for this (user, room).

    This is the root object under which we want to nest:
    - Per-turn spans (llm_turn)
    - Lightweight events (TTFT, dynamic context fetch, etc.)

    It is intentionally defensive to stay compatible with older SDKs that may
    not expose the newer trace/span hierarchy APIs.
    """
    lf = get_langfuse()
    if not lf:
        return None

    key = (user_name, room_name)
    if key in _session_traces:
        return _session_traces[key]

    env = environment or getattr(settings, "ENVIRONMENT", "prod")

    trace_obj: Optional[Any] = None
    try:
        # Preferred: explicit trace API in newer Langfuse SDKs
        if hasattr(lf, "trace"):
            trace_obj = lf.trace(
                name="session",
                user_id=user_name,
                session_id=room_name,
                metadata={
                    "user_name": user_name,
                    "room_name": room_name,
                    "environment": env,
                    "eval_run_id": eval_run_id,
                },
            )
        # Fallback: long-lived span as logical session root for older SDKs
        elif hasattr(lf, "start_span"):
            trace_obj = lf.start_span(
                name="session",
                metadata={
                    "user_name": user_name,
                    "room_name": room_name,
                    "environment": env,
                    "eval_run_id": eval_run_id,
                },
            )
    except Exception as e:  # pragma: no cover - non-critical
        logger.debug(f"Error creating Langfuse session trace/span: {e}")
        trace_obj = None

    if trace_obj is not None:
        _session_traces[key] = trace_obj

    return trace_obj


def write_debug_log(
    *,
    hypothesis_id: str,
    location: str,
    message: str,
    data: Optional[Dict[str, Any]] = None,
    run_id: str = "run1",
    session_id: str = "debug-session",
) -> None:
    """Append a single NDJSON debug log line to the shared debug log file.

    This is used for targeted debug-mode instrumentation and is safe to call from anywhere.
    """
    log_path = "/home/ranjit/pipecatBot/.cursor/debug.log"
    payload = {
        "sessionId": session_id,
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data or {},
        "timestamp": int(datetime.utcnow().timestamp() * 1000),
    }
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        # Never let debug logging break the app
        return


def _send_langfuse_event(
    name: str,
    properties: dict,
    *,
    user_name: Optional[str] = None,
    room_name: Optional[str] = None,
) -> None:
    """Send a lightweight Langfuse event using the available SDK methods.

    If a (user_name, room_name) is provided and a session trace/span exists,
    we try to attach the event to that trace so everything is grouped under a
    single Langfuse session in the UI.
    """
    lf = get_langfuse()
    if not lf:
        return

    try:
        # 1) Prefer attaching to an existing session trace/span if we can.
        if user_name and room_name:
            session_trace = get_or_create_session_trace(
                user_name=user_name,
                room_name=room_name,
            )
            if session_trace is not None:
                # Newer SDKs: dedicated event API on the trace object.
                if hasattr(session_trace, "event"):
                    try:
                        session_trace.event(name=name, metadata=properties)
                        return
                    except Exception:
                        # Fall through to client-level fallbacks.
                        pass

                # Fallback: represent the event as a very short-lived child span.
                if hasattr(session_trace, "start_span"):
                    span = session_trace.start_span(name=name, metadata=properties)
                    try:
                        span.end()
                    except Exception:
                        pass
                    return

        # 2) If we can't bind to a session trace, fall back to client-level APIs.
        if hasattr(lf, "event"):
            lf.event(name=name, properties=properties)
            return

        if hasattr(lf, "start_span"):
            span = lf.start_span(name=name, metadata=properties)
            try:
                span.end()
            except Exception:
                pass
            return
    except Exception as e:  # pragma: no cover - non-critical
        logger.debug(f"Error recording Langfuse event '{name}': {e}")


def record_context_fetch_event(
    *,
    user_name: str,
    room_name: str,
    intent_type: str,
    query_text: Optional[str],
    sessions_found: int,
    duration_ms: float,
) -> None:
    """Send a lightweight event to Langfuse for dynamic context fetching.

    This lets you see how context strategies affect latency and hit-rates.
    Safe no-op if Langfuse is not configured.
    """
    _send_langfuse_event(
        "dynamic_context_fetch",
        {
            "user_name": user_name,
            "room_name": room_name,
            "intent_type": intent_type,
            "query_text": (query_text or "")[:200],
            "sessions_found": sessions_found,
            "duration_ms": duration_ms,
        },
        user_name=user_name,
        room_name=room_name,
    )


def record_turn_metrics_event(
    *,
    user_name: str,
    room_name: str,
    ttft_ms: float,
    used_past_context: bool,
) -> None:
    """Send per-turn metrics (TTFT etc.) to Langfuse.

    This fires for every user→assistant turn, regardless of past context.
    """
    _send_langfuse_event(
        "turn_metrics",
        {
            "user_name": user_name,
            "room_name": room_name,
            "ttft_ms": ttft_ms,
            "used_past_context": used_past_context,
        },
        user_name=user_name,
        room_name=room_name,
    )


def record_llm_ttft_event(
    *,
    user_name: str,
    room_name: str,
    ttft_ms: float,
    model_name: Optional[str] = None,
) -> None:
    """Send model-only TTFT (LLM start -> first token) to Langfuse."""
    payload = {
        "user_name": user_name,
        "room_name": room_name,
        "ttft_ms": ttft_ms,
        "ttft_source": "llm",
    }
    if model_name:
        payload["model_name"] = model_name

    _send_langfuse_event(
        "llm_ttft",
        payload,
        user_name=user_name,
        room_name=room_name,
    )


def record_session_event(
    *,
    event_name: str,
    user_name: str,
    room_name: str,
    properties: Optional[dict] = None,
) -> None:
    """Send a session-level event to Langfuse (safe no-op if not configured)."""
    payload = {
        "user_name": user_name,
        "room_name": room_name,
    }
    if properties:
        payload.update(properties)

    _send_langfuse_event(
        event_name,
        payload,
        user_name=user_name,
        room_name=room_name,
    )

