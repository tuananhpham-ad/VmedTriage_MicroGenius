# Coding Convention - VMedTriage

## Principle

Use a domain-first, typed, and side-effect-light style.

The codebase should make the clinical workflow explicit in small modules:

- `src/config.py` owns runtime configuration, thresholds, and protocol constants.
- `src/models/` owns API and domain contracts.
- `src/services/` owns deterministic business capabilities.
- `src/agents/` owns orchestration only.
- `src/tool/catalog/` owns executable local tool contracts, policy enforcement, audit, and orchestration adapters.
- `src/tool/` outside `catalog/` owns external MCP descriptors and transports.
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
10. Every catalog tool must preserve a stable numeric id, name, input contract, output contract, and
    `execute(arguments, context)` entry point.
11. Invoke catalog tools through `CatalogToolRegistry.call()` or `ToolOrchestrator`; do not call shared
    handlers directly because that bypasses policy, output validation, and audit.
12. Return `CatalogToolResult` at tool boundaries. Tool-specific values belong in `data`; infrastructure
    errors belong in `error` and must set `ok=False`.
13. Mark EHR writes, workflow mutations, notifications, paging, scheduling, and feedback submission as
    side effects. They require an approved `ToolExecutionContext`.
14. Clinical Decision Support tool output is internal by default (`patient_visible=False`) and must not be
    copied directly into a patient response.
15. External integrations must distinguish queued/accepted from delivered. Never return `sent=True` or
    `delivered=True` without confirmation from the provider.
16. Local state adapters are for deterministic development and tests. Keep persistence behind replaceable
    state/repository boundaries.
17. Add a registry contract test when adding or changing a tool: discovery, output keys, risk policy, and
    at least one meaningful domain behavior.

## Tool implementation checklist

Before merging a new or changed tool, verify:

- `TOOL_SPEC` describes input, output, action, and a unique id/name.
- The handler returns every output key declared by `TOOL_SPEC`.
- PHI is not written to logs; audit records argument keys and operational metadata only.
- Failure has a safe fallback or routes to manual review.
- Side effects require explicit approval and are idempotent where the provider supports it.
- The patient-facing path still passes safety filtering and HITL approval.
