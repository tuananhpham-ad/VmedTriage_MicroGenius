from __future__ import annotations

SAMPLE_UPLOADED_DOCUMENTS = [
    {
        "title": "Chest pain triage protocol",
        "content": (
            "Patients reporting chest pain with shortness of breath, sweating, fainting, "
            "or pain radiating to the left arm, jaw, back, or shoulder should be prioritized "
            "for urgent nurse review or emergency escalation. Ask about onset, severity, "
            "radiation, breathing symptoms, and previous heart disease."
        ),
        "topic": "chest_pain",
        "tags": ["triage", "chest_pain", "red_flag"],
        "source": "sample_upload",
    },
    {
        "title": "Neurologic red flag protocol",
        "content": (
            "Sudden face droop, arm weakness, speech difficulty, confusion, seizure, "
            "or loss of consciousness can indicate a neurologic emergency. These cases "
            "should be routed to high priority human review and emergency care guidance."
        ),
        "topic": "neurologic",
        "tags": ["triage", "stroke", "red_flag"],
        "source": "sample_upload",
    },
    {
        "title": "Follow-up questions for incomplete triage",
        "content": (
            "When symptom details are incomplete, ask short follow-up questions about onset, "
            "severity, associated symptoms, risk factors, medication use, allergies, pregnancy, "
            "and whether symptoms are getting worse."
        ),
        "topic": "follow_up",
        "tags": ["triage", "follow_up", "checklist"],
        "source": "sample_upload",
    },
]

SAMPLE_QUERY = "What should the triage system do for chest pain with shortness of breath?"
