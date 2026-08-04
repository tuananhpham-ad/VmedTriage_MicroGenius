# Database ERD

ERD cho schema trong [`data/db_schema.sql`](../data/db_schema.sql).


```mermaid
erDiagram
    USERS ||--o{ PATIENT_PROFILES : owns
    PATIENT_PROFILES ||--o{ PATIENT_INSURANCES : has
    PATIENT_PROFILES ||--o{ CASES : has
    CASES ||--o{ CHECKLIST_RESPONSES : contains
    CASES ||--o{ AI_TRIAGE_SUGGESTIONS : receives
    USERS ||--o{ NURSE_SHIFTS : works
    USERS ||--o{ NURSE_TRIAGE_DECISIONS : makes
    NURSE_SHIFTS o|--o{ NURSE_TRIAGE_DECISIONS : context
    CASES ||--o{ NURSE_TRIAGE_DECISIONS : receives

    USERS {
        uuid id PK
        varchar email_or_phone UK
        varchar password_hash
        varchar role
        timestamptz created_at
    }

    PATIENT_PROFILES {
        uuid id PK
        uuid owner_user_id FK
        varchar full_name
        varchar relationship
        date date_of_birth
        varchar gender
        timestamptz created_at
        timestamptz updated_at
    }

    PATIENT_INSURANCES {
        uuid id PK
        uuid profile_id FK
        varchar insurance_number
        varchar provider_name
        date effective_from
        date effective_to
        boolean is_primary
        timestamptz created_at
    }

    CASES {
        uuid id PK
        uuid profile_id FK
        varchar symptom_group
        varchar status
        timestamptz created_at
        timestamptz updated_at
    }

    CHECKLIST_RESPONSES {
        uuid id PK
        uuid case_id FK
        varchar question_key
        text answer
        timestamptz answered_at
    }

    NURSE_SHIFTS {
        uuid id PK
        uuid nurse_id FK
        varchar shift_role
        timestamptz shift_start
        timestamptz shift_end
        varchar status
    }

    AI_TRIAGE_SUGGESTIONS {
        uuid id PK
        uuid case_id FK
        varchar classification
        numeric confidence
        text reasoning
        varchar model_name
        timestamptz created_at
    }

    NURSE_TRIAGE_DECISIONS {
        uuid id PK
        uuid case_id FK
        uuid nurse_id FK
        uuid shift_id FK
        varchar classification
        text note
        boolean is_current
        timestamptz decided_at
    }
```

## Triage workflow

```text
Checklist responses
        -> AI triage suggestion
        -> Nurse review
        -> Current nurse decision
```

`ai_triage_suggestions` chỉ là khuyến nghị của Agent. Kết quả chính thức phải
được lấy từ bản ghi hiện tại trong `nurse_triage_decisions`.
