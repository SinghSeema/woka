Langfuse Session Grouping Notes

This file documents how Langfuse traces are structured in the current codebase.

Key points:
- A session corresponds to a LiveKit room (room_name).
- A logical session is represented by:
  - A long–lived "session" span created when LangfuseMetrics is initialized.
  - Multiple child "llm_turn" spans created per user→assistant turn.
- When the SDK supports explicit trace / parent-child APIs, the code attempts
  to attach child spans to the session span. Otherwise, all spans are linked
  by common metadata: user_name, room_name, environment, eval_run_id.


