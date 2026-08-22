de# VMedTriage UI Design Contract

## Design read

VMedTriage is a regulated, accessibility-critical medical support product for two audiences: patients who need a calm guided intake and nurses who need a compact review workspace. The visual language is trust-first, restrained, and closer to a public service than a consumer wellness product.

## Taste Skill dials

- `DESIGN_VARIANCE: 3`
- `MOTION_INTENSITY: 2`
- `VISUAL_DENSITY: 5`

Patient screens should feel closer to density 3. Nurse screens may reach density 7 when the additional information supports a clinical decision.

## Foundation

- Stack: native HTML, CSS, and JavaScript served by the existing FastAPI app.
- Theme: a single light, clinical theme using semantic CSS variables. Do not invert individual sections into dark mode.
- Accent: medical blue `#1A5EA8`. Red is reserved for emergency and destructive meaning. Amber is reserved for missing information or early review. AI-confidence uses its own blue/grey/brown scale and must never reuse urgency colours.
- Shape rule: panels use 12-16px radius, controls use 9-10px radius, status badges may use a full pill.
- Motion: hover, press, and state feedback only. No decorative or perpetual motion.
- Type: IBM Plex Sans (400/500/600/700), with tabular figures for timestamps, case IDs, and other numerical values.

## Roles and information boundaries

### Patient

The patient may see:

- The fixed medical disclaimer.
- The conversation and follow-up questions.
- A clear emergency warning when a red flag is detected.
- Waiting, approved, or ask-for-more-information states.
- Guidance only after a nurse has approved it.

The patient must not see:

- Internal analysis.
- Structured mapping JSON.
- Raw AI priority or protocol reasoning.
- Nurse notes or incomplete clinical guidance.

### Nurse

The nurse may see:

- The case queue and priority proposal.
- Structured symptom summary and missing information.
- Red flags, protocol reason, and conversation history.
- Review controls for approve, edit priority, ask more, and escalate.

## Product priority mapping

The backend currently exposes five values while the PRD describes three patient-facing levels.

| Backend value | Nurse label | Patient-facing group |
|---|---|---|
| `Emergency` | Cấp cứu | Cấp cứu |
| `Urgent` | Khám sớm | Khám sớm |
| `Routine` | Khám thông thường | Tự theo dõi |
| `Self-care` | Tự theo dõi | Tự theo dõi |
| `Manual review` | Cần đánh giá thủ công | Chờ nhân viên y tế đánh giá |

The mapping is presentation-only. The UI must not silently rewrite backend data.

## Screen coverage

- W-01: role-aware demo access. It must not pretend to be production authentication.
- W-02: mandatory disclaimer before every new patient session.
- W-03: structured symptom intake with quick symptom-group choices and free text.
- W-04: immediate emergency warning that does not depend on nurse approval.
- W-05: collecting, waiting, approved, and error result states.
- W-06: nurse queue with empty, loading, stale/error, and populated states.
- W-07: case review with missing-data, red-flag, save-error, and completed states.

## Accessibility and safety

- WCAG AA contrast is the minimum.
- Interactive targets are at least 44px high.
- Focus is always visible.
- Status does not rely on color alone.
- Dynamic status and chat messages use appropriate live regions.
- Reduced-motion preference disables non-essential transitions.
- Mobile layouts must have no horizontal scroll at 390px.
- Patient-visible emergency content always includes the 115 instruction.

## Preserved contracts

- Existing API paths under `/api/v1` remain unchanged.
- Existing request and response schemas remain unchanged.
- Existing root route remains the demo application entry point.
- No new frontend dependency or build step is introduced.
