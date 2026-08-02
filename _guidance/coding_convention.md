# Coding Convention - VMedTriage

## Principle

Use a domain-first, typed, and side-effect-light style.

The codebase should make the clinical workflow explicit in small modules:

- `src/config.py` owns runtime configuration, thresholds, and protocol constants.
- `src/models/` owns API and domain contracts.
- `src/services/` owns deterministic business capabilities.
- `src/agents/` owns orchestration only.
- API routes should translate HTTP requests/responses and avoid business logic.

## Rules

1. Keep Gemma/LLM usage limited to semantic mapping and information extraction.
2. Do not let LLM output decide triage priority directly.
3. Route triage through validator, red-flag safety, protocol engine, summary, and HITL queue.
4. Use Pydantic models at module boundaries.
5. Prefer deterministic services with clear inputs and outputs.
6. Keep functions short and named by domain intent.
7. Store configurable thresholds, required fields, protocol rules, and red-flag definitions in `src/config.py`.
8. Do not send patient guidance before human approval.
9. Add tests for every new workflow branch that changes patient or nurse-facing behavior.
