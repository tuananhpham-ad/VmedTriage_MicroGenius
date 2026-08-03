"""Tool stub: translate clinical text."""

TOOL_SPEC = {
    "id": 3,
    "name": "medical_translation_tool",
    "description": "Translate patient or guideline text between Vietnamese and English with clinical term preservation.",
    "input": {"text": "Text to translate.", "source_language": "Source language.", "target_language": "Target language."},
    "output": {"translated_text": "Translated text.", "preserved_terms": "Clinical terms kept stable."},
    "action": "Translate text for guideline lookup or patient-safe communication.",
}

# TODO: Implement MCP/local adapter.
