from django.conf import settings
from openai import OpenAI


LANGUAGE_NAMES = {
    "ko": "Korean",
    "en": "English",
    "ja": "Japanese",
    "zh": "Chinese",
}


def translate_medical_message(
    text,
    source_language,
    target_language,
):
    if source_language == target_language:
        return text

    client = OpenAI()

    source_name = LANGUAGE_NAMES.get(
        source_language,
        source_language,
    )
    target_name = LANGUAGE_NAMES.get(
        target_language,
        target_language,
    )

    response = client.responses.create(
        model=settings.OPENAI_TRANSLATION_MODEL,
        reasoning={"effort": "low"},
        store=False,
        instructions=(
            "You are a professional medical translator. "
            "Translate the message faithfully without adding, "
            "removing, summarizing, or interpreting information. "
            "Preserve medication names, dosages, units, numbers, "
            "dates, anatomical terms, negations, and uncertainty. "
            "Do not provide medical advice. "
            "Return only the translated message."
        ),
        input=(
            f"Source language: {source_name}\n"
            f"Target language: {target_name}\n"
            f"Message:\n{text}"
        ),
    )

    translated_text = response.output_text.strip()

    if not translated_text:
        raise ValueError(
            "OpenAI가 빈 번역 결과를 반환했습니다."
        )

    return translated_text