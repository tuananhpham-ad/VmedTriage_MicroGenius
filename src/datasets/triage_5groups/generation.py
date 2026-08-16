"""Constrained question generation for the dataset builder.

The generator never determines a label or fabricates a patient follow-up.  In
offline mode it uses the catalog wording, which makes the build reproducible.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

DISALLOWED = ("chẩn đoán", "bệnh gì", "kê đơn", "uống thuốc", "điều trị")


@dataclass(frozen=True)
class GeneratedQuestion:
    question: str
    follow_up_choice_index: int
    provider: str


def _validate_question(question: str, candidate_count: int, choice_index: int) -> GeneratedQuestion:
    question = " ".join(question.split())
    if not question.endswith("?") or len(question) > 500:
        raise ValueError("generated agent question must be a direct question of at most 500 characters")
    if any(value in question.casefold() for value in DISALLOWED):
        raise ValueError("generated agent question contains prohibited wording")
    if not 0 <= choice_index < candidate_count:
        raise ValueError("follow-up choice is outside the allowed candidates")
    return GeneratedQuestion(question=question, follow_up_choice_index=choice_index, provider="gemini")


class QuestionGenerator:
    def __init__(self, cache_path: Path, use_gemini: bool = False, model: str = "gemini-3.5-flash") -> None:
        self.cache_path = cache_path
        self.use_gemini = use_gemini
        self.model = model
        self.cache: dict[str, dict] = {}
        if cache_path.exists():
            for line in cache_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    entry = json.loads(line)
                    self.cache[entry["key"]] = entry

    def generate(self, key: str, fallback_question: str, candidates: list[str], ordinal: int) -> GeneratedQuestion:
        if key in self.cache:
            entry = self.cache[key]
            if entry["provider"] == "gemini" or not self.use_gemini:
                if entry["provider"] != "gemini":
                    return GeneratedQuestion(entry["question"], entry["follow_up_choice_index"], entry["provider"])
                return _validate_question(entry["question"], len(candidates), entry["follow_up_choice_index"])

        choice = ordinal % len(candidates)
        result = GeneratedQuestion(fallback_question, choice, "rule_template")
        if self.use_gemini:
            result = self._generate_with_gemini(fallback_question, candidates, choice)
        self.cache[key] = {
            "key": key,
            "provider": result.provider,
            "model": self.model if result.provider == "gemini" else None,
            "question": result.question,
            "follow_up_choice_index": result.follow_up_choice_index,
        }
        return result

    def _generate_with_gemini(self, fallback_question: str, candidates: list[str], choice: int) -> GeneratedQuestion:
        from google import genai

        prompt = (
            "Viết lại một câu hỏi sàng lọc tiếng Việt ngắn, trung tính. Không chẩn đoán, kê đơn, "
            "điều trị hoặc đánh giá mức độ. Chỉ trả JSON có agent_question và follow_up_choice_index. "
            f"Câu hỏi gốc: {fallback_question}\n"
            f"Các follow-up được phép chọn: {json.dumps(candidates, ensure_ascii=False)}\n"
            f"Index mặc định hợp lệ: {choice}"
        )
        response = genai.Client().models.generate_content(model=self.model, contents=prompt)
        text = re.sub(r"^```(?:json)?|```$", "", (response.text or "").strip(), flags=re.MULTILINE).strip()
        payload = json.loads(text)
        return _validate_question(payload["agent_question"], len(candidates), payload["follow_up_choice_index"])

    def save(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        rows = [json.dumps(self.cache[key], ensure_ascii=False, sort_keys=True) for key in sorted(self.cache)]
        self.cache_path.write_text("\n".join(rows) + ("\n" if rows else ""), encoding="utf-8")
