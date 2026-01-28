# Turn-by-Turn Observability Implementation

## Overview

This document describes the event-based observability system that provides turn-by-turn metrics and tracing without blocking the pipeline.

## Architecture

### Components

1. **LangfuseMetrics Processor** (`backend/bot/services/langfuse_metrics.py`)
   - Observes frames as they flow through the pipeline
   - Creates turn-level traces in Langfuse and OpenTelemetry
   - Non-blocking: all operations are async and fire-and-forget

2. **Event-Based Context Observer** (`backend/bot/handlers/events.py`)
   - Replaces periodic polling (500ms) with event-driven monitoring
   - Triggers on context message count changes
   - Zero latency: processes messages immediately when they change

3. **Enhanced Observability Helpers** (`backend/app/core/observability.py`)
   - Existing helpers enhanced with eval tagging support
   - Turn-level metrics with `used_past_context` flag

## Key Features

### 1. Non-Blocking Pipeline Observability

- **LangfuseMetrics processor** uses `asyncio.create_task()` for all observability operations
- Never blocks frame processing
- Errors are caught and logged but never raise exceptions

### 2. Event-Based Monitoring

**Before (Polling):**
```python
# Checked every 500ms - up to 500ms latency
async def periodic_monitor():
    while True:
        await asyncio.sleep(0.5)
        await monitor_messages()
```

**After (Event-Based):**
```python
# Triggers immediately when context changes
class ContextObserver:
    def get_messages(self):
        msgs = self._context.get_messages()
        if count_changed:
            asyncio.create_task(self._on_message_changed(msgs))
        return msgs
```

### 3. Turn-by-Turn Tracing

Each user→assistant turn creates:
- **OpenTelemetry span**: `llm_turn` with attributes (user_name, room_name, turn_id, ttft_ms)
- **Langfuse trace**: Full trace with user message span and assistant response span
- **Metrics**: TTFT, token counts, context usage flags

### 4. Eval Support

- Automatic detection: rooms starting with `eval_` or `ENVIRONMENT=eval`
- Eval tagging: `eval_run_id`, `environment="eval"` in all traces
- Easy filtering in Langfuse dashboards

## Pipeline Integration

```python
# In main.py
pipeline = Pipeline([
    transport.input(),
    stt,
    context_aggregator.user(),
    llm,
    langfuse_metrics,  # ← Observes frames here
    tts,
    transport.output(),
    context_aggregator.assistant(),
])
```

## Metrics Captured

### Per Turn
- **TTFT** (Time To First Token): Measured from user message to assistant response
- **Token counts**: Input/output tokens (if available from LLM frames)
- **Context usage**: Whether past context was injected
- **Environment**: `prod`, `eval`, or `dev`
- **Eval run ID**: For eval runs

### Per Session
- Total turns
- Average TTFT
- Total tokens
- Error counts

## Performance Impact

### Before
- **Latency**: Up to 500ms delay (polling interval)
- **CPU**: Constant polling even when idle
- **Accuracy**: TTFT measurements off by up to 500ms

### After
- **Latency**: ~0ms (event-driven)
- **CPU**: Only processes when messages change
- **Accuracy**: Exact TTFT measurements

## Usage

### For Production
```python
# Automatically enabled if ENABLE_LANGFUSE or ENABLE_TRACING is True
# No code changes needed
```

### For Eval Runs
```python
# Create room with eval_ prefix
room_name = "eval_my_test_suite_001"

# Or set environment
ENVIRONMENT=eval
```

## Langfuse Dashboard

View turn-by-turn metrics in Langfuse:
1. **Traces**: Filter by `environment="eval"` or `environment="prod"`
2. **Events**: See `turn_metrics` events with TTFT and context usage
3. **Scores**: Add custom scores for eval examples (future enhancement)

## OpenTelemetry Traces

View in Jaeger/Tempo:
1. Service: `woka-bot`
2. Operation: `llm_turn`
3. Attributes: `user_name`, `room_name`, `turn_id`, `ttft_ms`, `eval_run_id`

## Future Enhancements

1. **LLM-as-Judge**: Add automatic scoring for eval examples
2. **Custom Metrics**: Add domain-specific metrics (e.g., wellness coaching quality)
3. **Alerts**: Configure alerts for TTFT regressions or eval failures
4. **A/B Testing**: Compare prompt/model variants using eval_run_id

