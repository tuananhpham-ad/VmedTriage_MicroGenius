# Handoff: VMedTriage UI

## Overview
VMedTriage is a medical triage platform: patients describe symptoms to an AI chat assistant, the assistant proposes an urgency level, and a nurse/clinician reviews and confirms the final priority before any guidance reaches the patient (human-in-the-loop). This handoff covers the mobile-primary flow and the desktop/web flow (including a public pre-login landing page).

## About the Design Files
The files in this bundle are **design references built in HTML** (`VMedTriage.dc.html` = mobile-primary screens, `VMedTriage Web.dc.html` = desktop/web screens incl. public landing). They are prototypes showing intended look, content and interaction — not production code to copy directly. Recreate these screens in the target codebase's existing framework/component library and state-management patterns. If no framework exists yet, React + a lightweight state layer is a reasonable default given the interaction complexity (chat, dropdowns, form validation).

## Fidelity
**High-fidelity.** Colors, typography, spacing, copy (Vietnamese) and states are final/near-final. Recreate pixel-close using the target codebase's own component primitives (buttons, inputs, cards) rather than introducing new ones, unless none exist.

## Design Tokens

**Colors**
- Primary (medical blue): `#1A5EA8`, hover/pressed `#144C8A`, tint bg `#EAF2FB`, tint border `#CFE0F3`, deep text-on-tint `#154E8C`
- Emergency/red (Cấp cứu, red-flag, errors): base `#C62828`, hover `#A81F1F`, tint bg `#FDECEC`/`#FBE3E3`, tint border `#F0B9B9`, deep text `#8E1F1F`
- Warning/amber (Khám sớm, missing-info, stale-data): base `#D68A00`/`#A34F00`, tint bg `#FFF6E5`/`#FFF1E3`, tint border `#F0DCAE`/`#F2CFAA`, deep text `#7A5200`/`#8A5B00`
- Success/green (Tự theo dõi, approved, confirmations): base `#1E7A4D`, tint bg `#E9F7F0`, tint border `#BFE5D2`, deep text `#166341`
- Neutrals: page bg `#EDF1F5` / `#F7F9FB`, card bg `#fff`, card border `#E3E8EF`/`#DCE3EA`, divider `#EEF1F5`, body text `#16202B`, secondary text `#5B6B7C`/`#3D4C5B`, muted/placeholder text `#8494A4`/`#9AA7B4`/`#93A1B0`, disabled bg `#E4E8ED`
- AI-confidence scale (distinct from priority colors, so the two don't get confused): Cao (high) `#1A5EA8`, Trung bình (medium) `#5B6B7C`, Thấp (low) `#A34F00`

**Typography**: IBM Plex Sans (weights 400/500/600/700), loaded from Google Fonts. Body text-color `#16202B`. Key sizes: hero headline 48px/600, section title 27–30px/600, card title 16–19px/600, body 14.5–17px/400–500, small/meta 11.5–13px/500–600 (labels often uppercase with `letter-spacing:.07–.1em`). Tabular figures (`font-variant-numeric: tabular-nums`) on all numeric/ID/timestamp values.

**Spacing / radius**: cards use 12–16px border-radius, pills/badges use 999px (fully round), buttons 9–10px. Card padding 16–22px (mobile) / 18–26px (web). Grid gaps 14–24px.

**Shadows**: outer app-frame shadow `0 18px 44px rgba(22,32,43,.10)`; small floating menus `0 6px 18px rgba(22,32,43,.08)`; subtle card lift `0 1px 2–3px rgba(22,32,43,.05)`.

**Focus/hover**: `outline: 2px solid #1A5EA8; outline-offset: 2px` on `:focus-visible` for inputs/buttons. Buttons/links get a defined `:hover` (usually one step deeper on the same color, or a light tint background).

## Screens / Views

### Public landing (web only, pre-login) — "W-00P"
- **Purpose**: First thing an unauthenticated visitor sees. Explains what the product is and does, drives to login/signup.
- **Layout**: Full-width card (max-width 1320px) inside the app frame. Sections top-to-bottom: transparent nav (logo + "Cách hoạt động"/"Về chúng tôi" text links + outlined "Đăng nhập" button, right-aligned) → hero (2-col grid: headline/subhead/CTA left, illustration right, soft radial-ring decoration + heartbeat SVG line + an `image-slot`-style photo placeholder masked into an organic blob shape) → "Cách hoạt động" 3-step card grid (numbered 01/02/03, icon, title, description) → 2-col image+text band (photo left, "AI không được phép tự gửi kết luận" copy + 2 checklist bullets right) → 3-stat trust row (100% / <3 phút / 24/7) → gradient CTA band (headline + "Đăng nhập / Đăng ký" button) → footer (copyright + "Không phải dịch vụ cấp cứu, gọi 115" disclaimer).
- **Photo placeholders**: two — hero (blob-masked, ~380×380) and the "team" band photo (full-bleed rect). Source real photography for these; do not ship literal color-block placeholders to production.
- **CTAs**: "Bắt đầu khai báo triệu chứng" and the nav/footer "Đăng nhập" all route to the login screen (unauthenticated).

### W-01 Đăng nhập / Đăng ký (Login/Register)
- Shared by patient and staff roles. Mobile: single centered card. Web: 2-col — left panel (brand statement + 3 trust bullets, tinted bg), right panel (the actual form).
- Fields: email/phone, password (show/hide toggle), confirm-password (register only), full name (register only), "Ghi nhớ đăng nhập" checkbox + "Quên mật khẩu?" (login only), role selector (segmented: Bệnh nhân / Nhân viên y tế).
- Submit button disabled (grey, `not-allowed`) until email+password are non-empty; becomes primary-blue when ready.
- Error state: red banner "Email hoặc mật khẩu không đúng" above the form. Mobile also has a network-error variant.

### W-02 Disclaimer
- One-time-per-session, non-dismissible-except-by-CTA screen. Numbered list (1–3, blue circular index) stating: (1) **the AI's scope is explicitly limited** — "chỉ hỏi triệu chứng và đề xuất mức độ khẩn cấp — không chẩn đoán bệnh, không kê đơn thuốc" (this exact scoping language matters, see "AI-transparency notes" below); (2) all suggestions are nurse-confirmed before reaching the patient; (3) call 115 for real emergencies instead of waiting in-app. Single full-width primary CTA "Tôi đã hiểu, bắt đầu".

### W-03 Khai báo triệu chứng (Symptom chat)
- Chat UI: agent bubbles left (light), patient bubbles right (blue fill), centered pill "system" messages (e.g. "Đã nhận diện: Đau ngực") for recognized symptom groups.
- **Capability strip**: a persistent small info bar directly under/near the chat header — info icon + "Trợ lý AI chỉ hỏi triệu chứng và đề xuất mức độ khẩn cấp — không chẩn đoán bệnh. Nhân viên y tế sẽ xác nhận trước khi gửi kết quả." Keep this visible (not just in the one-time disclaimer) since it's the active AI-interaction surface.
- Input row: text field + send button; Enter key sends. Offline variant: red banner "Mất kết nối, đang thử kết nối lại..." and input disabled/dimmed.
- Web adds a right sidebar: "Nhóm đã nhận diện" (detected symptom group), a checklist progress card (n/7 fields collected, progress bar, per-item done/pending icon), and a data-use note card.
- Empty-state variant shows only the assistant's opening message.

### W-04 Red-flag (Emergency interstitial)
- Full-screen/full-card takeover, red as the dominant color (only screen where this is true) — red header bar "CẢNH BÁO KHẨN CẤP", large warning-triangle icon, headline "Dấu hiệu cần cấp cứu: {reason}", explanatory copy, a green-check confirmation chip ("Ca của bạn đã được chuyển ngay... mức ưu tiên cao nhất"), a 115 hotline chip, single red CTA "Tôi đã đọc, tiếp tục".

### W-05 Kết quả (Result)
- Three states: **pending** (spinner, "Đang chờ nhân viên y tế duyệt", ETA chip ~5-10 phút), **approved** (green "Đã duyệt bởi nhân viên y tế" chip; final-priority card with colored dot + label + numbered treatment instructions; a metadata card: symptom group / approver name / approval timestamp), **error** (muted icon, "Không thể tải kết quả", retry button).
- Always ends with the disclaimer line "Đây không phải chẩn đoán, hãy gặp bác sĩ để được tư vấn đầy đủ."

### W-06 Hàng đợi (Nurse queue) — staff-facing
- Header: logo, tab nav (Hàng đợi / Ca đã duyệt / Log audit), signed-in nurse identity (name, shift, avatar initials).
- Summary chips: counts per priority (Cấp cứu / Khám sớm / Tự theo dõi), each with its priority dot color.
- Table/list, sorted emergency-first then by wait time. Emergency rows get a red left-border + red 1.5px border treatment (visually distinct from normal rows). Each row: status dot, patient code, symptom group, **priority badge + an "Độ tin cậy AI: {Cao/Trung bình/Thấp}" sub-line directly under the badge** (own color scale, see tokens — deliberately not reusing red/amber/green so it never gets misread as another priority signal), wait time, "Duyệt ca →" link. Row click opens W-07.
- States: stale (amber banner "Không tải được danh sách mới nhất..." + retry), empty (green check illustration + "Không có ca nào đang chờ duyệt"), list (auto-refresh/polling indicator at the bottom).

### W-07 Duyệt ca (Case review, HITL checkpoint) — staff-facing
- 2-col layout: left = case summary card (all collected fields, "Thiếu thông tin" amber tag on any missing field, plus two small provenance lines: which checklist version detected symptoms, which clinical guideline grounds the conclusion) + (web only) the full chat transcript; right = red-flag callout (if any), **AI-priority card showing the proposed priority AND a confidence badge ("Độ tin cậy: {level}") in its top-right corner**, then the action stack.
- Actions (top to bottom): **Duyệt nguyên trạng** (approve as-is, primary blue) → **Chỉnh sửa mức ưu tiên** (dropdown: Cấp cứu/Khám sớm/Tự theo dõi, each with its dot color and a checkmark on the active one) → **Từ chối ca** (opens a required-reason textarea; confirm button disabled until reason is non-empty) → divider → **Hỏi thêm** ("ask more" — opens an inline chat panel where the nurse joins/replaces the agent, sends her own question, and takes over final-priority decision from that point; explicit copy states the AI's suggestion is no longer used once this path is taken).
- States: default, reject-open, save-error (top-bar shows a locked/greyed "Đang khoá — chưa lưu được quyết định" chip in place of the back button).

## AI-transparency notes (recently added — preserve intent, not just literal copy)
Two Microsoft "Guidelines for Human-AI Interaction" principles were deliberately built into this design and should survive re-implementation:
- **G1 – make capabilities explicit**: every AI-facing surface (disclaimer, chat capability strip) states the assistant's scope is limited to *asking about symptoms and proposing an urgency tier* — never diagnosis, never prescriptions. Don't let a rewrite drift this back to generic "AI hỗ trợ" language.
- **G2 – make capability limits (confidence) explicit**: every place a nurse sees an AI-proposed priority (queue rows, review panel) must also show a confidence indicator (Cao/Trung bình/Thấp) in its own neutral color scale, distinct from the red/amber/green urgency colors, so nurses can weight how much to trust the suggestion.

## Interactions & Behavior
- Priority dropdown, reject-reason and ask-more panels are simple open/close + controlled-input state (see State Management).
- Nothing auto-submits: reject and ask-more both require non-empty text before their confirm button enables.
- Queue rows and result screens are read-heavy; the only "live" async behavior implied is polling (queue) and websocket-like chat (symptom intake) — implement with your app's existing data-fetching pattern, this prototype does not prescribe an API shape.
- Chat "send" on Enter or button click appends the patient message + a canned follow-up agent question (prototype-only; wire to your real agent backend).

## State Management
Suggested state shape per screen (rename to fit your app):
- **Auth**: `tab` (login|register), `email`, `password`, `showPassword`, `role` (patient|staff)
- **Chat (W-03)**: `messages[]` (role: agent|patient|system, text), `draft`, `connectionState` (live|offline)
- **Review (W-07)**: `priority` (current selection), `priorityMenuOpen`, `rejectOpen` + `rejectReason`, `askOpen` + `askDraft`, `saveState` (idle|error)
- **Queue (W-06)**: `cases[]` (code, symptomGroup, priority, aiConfidence, waitTime), `loadState` (ok|stale|empty)
- Each case object should carry both `priority` and `aiConfidence` as separate fields end-to-end from whatever service proposes them, since the UI always renders both together.

## Assets
- Logo mark: rounded-square outline + a heartbeat/pulse line inside, wordmark "VMed**Triage**" (Triage in brand blue). Recreate as an SVG/icon component, not an image.
- Icons throughout are simple 1.5–2px stroke line icons (no fill), ad-hoc inline SVG in the prototype — swap for your icon library's closest equivalents (warning triangle, checkmark, chat bubble, chevron, eye/eye-off, shield/lock, heart-pulse, stethoscope-ish check, phone/emergency).
- Two photo placeholders on the public landing page (`image-slot` elements in the prototype) need real photography before ship: a hero image (patient/assistant or clinician moment, blob-masked) and a wide band image (nurse reviewing a case). Neither has a final image yet.

## Files
- `VMedTriage.dc.html` — mobile-primary screens (W-01 through W-07), with a top toolbar for switching screens/state variants (dev/QA aid only, not part of the product UI).
- `VMedTriage Web.dc.html` — desktop/web screens, including the public pre-login landing page (W-00P), the authenticated patient homepage (W-00), and wider-breakpoint versions of W-01–W-07. Same dev toolbar convention.
- `image-slot.js` — prototype-only drag/drop image placeholder component; not for production use, just marks where real photography goes.
