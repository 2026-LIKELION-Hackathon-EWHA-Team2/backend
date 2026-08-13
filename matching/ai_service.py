import json

from django.conf import settings
from openai import OpenAI

from accounts.models import MedicalSpecialty


client = OpenAI()


def analyze_required_specialty(
    symptom_case,
):
    """
    환자가 입력한 증상 정보를 분석하여
    DB에 존재하는 진료과 중 가장 적절한 하나를 선택한다.
    """

    # -------------------------
    # 증상 부위
    # -------------------------

    areas = []

    for area in symptom_case.areas.all():
        if area.area_type == "OTHER":
            areas.append(
                area.custom_area
            )
        else:
            areas.append(
                area.get_area_type_display()
            )

    # -------------------------
    # 증상 종류
    # -------------------------

    symptom_types = []

    for symptom in symptom_case.symptom_types.all():
        if symptom.symptom_type == "OTHER":
            symptom_types.append(
                symptom.custom_symptom
            )
        else:
            symptom_types.append(
                symptom.get_symptom_type_display()
            )

    # -------------------------
    # 증상 발생 시점
    # -------------------------

    onset_timing = "정보 없음"

    if symptom_case.onset_timing:
        onset_timing = (
            symptom_case.get_onset_timing_display()
        )

    # -------------------------
    # 통증 정도
    # -------------------------

    pain_level = (
        symptom_case.pain_level
        if symptom_case.pain_level is not None
        else "정보 없음"
    )

    # -------------------------
    # 추가 설명
    # -------------------------

    description = (
        symptom_case.description
        or "추가 설명 없음"
    )

    # -------------------------
    # 증상 시작 날짜
    # -------------------------

    symptom_start_date = (
        str(symptom_case.symptom_start_date)
        if symptom_case.symptom_start_date
        else "정보 없음"
    )

    # -------------------------
    # 현재 DB에 존재하는 진료과 목록
    # -------------------------

    available_specialties = list(
        MedicalSpecialty.objects
        .values_list(
            "specialty_name",
            flat=True,
        )
        .distinct()
    )

    if not available_specialties:
        return None

    specialty_list = "\n".join(
        f"- {specialty}"
        for specialty in available_specialties
    )

    prompt = f"""
너는 해외 병원 추천 서비스의 진료과 분류 시스템이다.

환자가 입력한 증상 정보를 바탕으로
아래 제공된 진료과 중 가장 적절한 진료과 하나를 선택한다.

의학적 진단을 내리는 것이 아니라,
환자에게 적절한 병원 분야를 연결하기 위한
분류 작업만 수행한다.

[환자 증상 정보]

증상 부위:
{", ".join(areas) if areas else "정보 없음"}

증상 종류:
{", ".join(symptom_types) if symptom_types else "정보 없음"}

증상 발생 시점:
{onset_timing}

증상 시작 날짜:
{symptom_start_date}

통증 정도:
{pain_level} / 5

환자 추가 설명:
{description}


[선택 가능한 진료과]

{specialty_list}


중요:
- 반드시 위 목록에 존재하는 진료과 중 하나만 선택한다.
- 진료과 이름을 임의로 수정하거나 번역하지 않는다.
- 제공된 진료과 이름을 정확히 그대로 반환한다.

다음 JSON 형식으로만 응답한다.

{{
    "required_specialty": "진료과 이름"
}}
"""

    response = client.responses.create(
        model=settings.OPENAI_MATCHING_MODEL,
        input=prompt,
    )

    result = json.loads(
        response.output_text
    )

    required_specialty = result.get(
        "required_specialty"
    )

    if (
        required_specialty
        not in available_specialties
    ):
        return None

    return required_specialty