# Matching API 명세서

## 1. 개요

환자가 제출한 증상 케이스를 AI로 분석하고, 위치·전문분야·협진 경험을 기준으로 병원을 추천하며, 추천 병원 선택과 매칭 동의를 처리하는 API다.

### 1.1 공통 정보

| 항목 | 내용 |
|---|---|
| Base URL | `/api/matching/` |
| 인증 | 필수 |
| 인증 방식 | JWT 또는 Django Session |
| JWT 헤더 | `Authorization: Bearer {access_token}` |
| 기본 요청 형식 | `application/json` |
| 기본 응답 형식 | `application/json` |
| 페이지네이션 | 없음 |

모든 엔드포인트에 `IsAuthenticated`가 적용되어 있다. 실질적으로는 `PatientProfile`이 존재하는 환자만 이용할 수 있으며, 환자 프로필이 없으면 `403 Forbidden`을 반환한다.

### 1.2 API 목록

| 기능 | Method | Path |
|---|---|---|
| 매칭 요청 생성 및 추천 실행 | `POST` | `/api/matching/requests/` |
| 매칭 요청 상세 조회 | `GET` | `/api/matching/requests/{match_request_id}/` |
| 선택 병원 매칭 동의 | `PATCH` | `/api/matching/requests/{match_request_id}/consent/` |
| 추천 병원 목록 조회 | `GET` | `/api/matching/requests/{match_request_id}/recommendations/` |
| 추천 병원 선택 | `POST` | `/api/matching/recommendations/{recommendation_id}/select/` |

현재 Matching API에는 Query Parameter를 사용하는 엔드포인트가 없다.

---

## 2. 공통 Enum 및 규칙

### 2.1 위치 출처 `location_source`

| 값 | 의미 | 위치 입력 방식 |
|---|---|---|
| `PROFILE` | 환자 프로필 위치 | 서버가 환자 프로필의 위치를 복사 |
| `CUSTOM` | 직접 지정 위치 | 요청의 `search_*` 값 사용 |

`location_source`를 생략하면 `PROFILE`이 기본값이다.

#### `PROFILE` 처리

다음 환자 프로필 값을 매칭 요청의 검색 위치 스냅샷으로 저장한다.

| 환자 프로필 | 매칭 요청 |
|---|---|
| `residence_country` | `search_country` |
| `city` | `search_city` |
| `address` | `search_address` |
| `latitude` | `search_latitude` |
| `longitude` | `search_longitude` |

`residence_country`, `latitude`, `longitude`가 없으면 요청할 수 없다. 클라이언트가 `search_*` 값을 함께 보내더라도 프로필 값으로 덮어쓴다.

#### `CUSTOM` 처리

`search_country`, `search_latitude`, `search_longitude`가 필수다. `search_city`와 `search_address`는 선택값이다.

### 2.2 매칭 요청 상태 `status`

| 값 | 의미 |
|---|---|
| `PENDING` | 대기 |
| `ANALYZING` | AI 분석 중 |
| `COMPLETED` | 추천 생성 완료 |
| `SELECTED` | 병원 선택 완료 |
| `CANCELLED` | 취소 |

`status`는 읽기 전용이며 서버가 관리한다.

현재 AI 분석 실패 시 매칭 요청 상태는 `PENDING`으로 복구되고 증상 케이스 상태는 `SUBMITTED`로 복구된다.

### 2.3 전문분야 코드 `required_specialty_code`

AI가 증상을 분석한 뒤 전문분야 이름과 안정적인 코드를 함께 저장한다.

| 값 | 의미 |
|---|---|
| `ACNE_SCAR` | 여드름·흉터 |
| `PIGMENTATION` | 색소 |
| `LIFTING` | 리프팅 |
| `BOTOX_FILLER` | 보톡스·필러 |
| `BREAST_BODY` | 가슴·바디 |
| `EYE` | 눈 |
| `NOSE` | 코 |
| `CONTOURING` | 윤곽 |
| `HAIR_REMOVAL` | 제모 |
| `CUSTOM` | 사용자 정의 전문분야 |

### 2.4 추천 가중치

| 필드 | 기본값 | 허용 범위 |
|---|---:|---:|
| `specialty_weight` | 50 | 0~100 |
| `distance_weight` | 50 | 0~100 |
| `collaboration_weight` | 50 | 0~100 |

세 값이 모두 0일 수는 없다. 가중치의 합이 100일 필요는 없으며 서버가 전체 합으로 정규화한다.

```text
total_score =
  (specialty_score × specialty_weight
   + distance_score × distance_weight
   + collaboration_score × collaboration_weight)
  / 전체 가중치 합
```

### 2.5 점수 계산 기준

#### 전문분야 점수

- 전문분야 코드 또는 정규화된 전문분야 이름이 일치하면 `100`
- 일치하지 않으면 `0`

#### 거리 점수

| 거리 | 점수 |
|---:|---:|
| 2km 이하 | 100 |
| 5km 이하 | 90 |
| 10km 이하 | 80 |
| 20km 이하 | 60 |
| 50km 이하 | 40 |
| 50km 초과 | 20 |

#### 협진 점수

해당 병원이 상대 병원으로 참여한 `TRANSFERRED` 의료 케이스 수를 사용한다.

| 협진 건수 | 점수 |
|---:|---:|
| 10건 이상 | 100 |
| 5~9건 | 80 |
| 1~4건 | 60 |
| 0건 | 20 |

#### 병원 필터 및 추천 개수

- 병원 계정에 연결된 병원 프로필만 평가한다.
- 위도 또는 경도가 없는 병원은 제외한다.
- `search_country`와 병원 `country`가 정확히 일치하지 않으면 제외한다.
- 총점 내림차순으로 정렬한다.
- 최대 20개를 반환한다.
- 5개 단위로 `batch_number`를 부여한다.

---

## 3. 공통 응답 객체

### 3.1 매칭 요청 객체

```json
{
  "match_request_id": 12,
  "symptom_case": 31,
  "patient_id": 7,
  "required_specialty": "색소",
  "required_specialty_code": "PIGMENTATION",
  "specialty_weight": 50,
  "distance_weight": 30,
  "collaboration_weight": 20,
  "location_source": "PROFILE",
  "search_country": "KR",
  "search_city": "Seoul",
  "search_address": "Gangnam-gu",
  "search_latitude": "37.4979000",
  "search_longitude": "127.0276000",
  "personal_information_provision_agreed": false,
  "information_items_purpose_confirmed": false,
  "medical_consultation_use_agreed": false,
  "withdrawal_right_confirmed": false,
  "agreed_at": null,
  "status": "COMPLETED",
  "created_at": "2026-08-16T12:00:00+09:00",
  "updated_at": "2026-08-16T12:00:05+09:00"
}
```

#### 필드 설명

| 필드 | 형식 | Nullable | 쓰기 가능 | 설명 |
|---|---|---:|---:|---|
| `match_request_id` | integer | X | X | 매칭 요청 PK |
| `symptom_case` | integer | X | O | 증상 케이스 ID |
| `patient_id` | integer | X | X | 환자 프로필 ID |
| `required_specialty` | string | O | X | AI 분석 전문분야 이름 |
| `required_specialty_code` | enum | O | X | AI 분석 전문분야 코드 |
| `specialty_weight` | integer | X | O | 전문분야 가중치 |
| `distance_weight` | integer | X | O | 거리 가중치 |
| `collaboration_weight` | integer | X | O | 협진 경험 가중치 |
| `location_source` | enum | X | O | 위치 출처 |
| `search_country` | string | X | 조건부 | 검색 국가 스냅샷 |
| `search_city` | string | O | 조건부 | 검색 도시 스냅샷 |
| `search_address` | string | O | 조건부 | 검색 주소 스냅샷 |
| `search_latitude` | decimal string | X | 조건부 | 검색 위도, 소수점 7자리 |
| `search_longitude` | decimal string | X | 조건부 | 검색 경도, 소수점 7자리 |
| `personal_information_provision_agreed` | boolean | X | 동의 API만 | 개인정보 제공 동의 |
| `information_items_purpose_confirmed` | boolean | X | 동의 API만 | 제공 항목·목적 확인 |
| `medical_consultation_use_agreed` | boolean | X | 동의 API만 | 의료 상담 활용 동의 |
| `withdrawal_right_confirmed` | boolean | X | 동의 API만 | 철회 권리 확인 |
| `agreed_at` | datetime | O | X | 네 동의가 모두 완료된 시각 |
| `status` | enum | X | X | 매칭 요청 상태 |
| `created_at` | datetime | X | X | 생성 시각 |
| `updated_at` | datetime | X | X | 수정 시각 |

### 3.2 전문분야 객체

```json
{
  "hospital_specialty_id": 4,
  "specialty_code": "PIGMENTATION",
  "specialty_name": "색소",
  "is_custom": false
}
```

### 3.3 병원 요약 객체

```json
{
  "hospital_id": 3,
  "name": "예시병원",
  "country": "KR",
  "city": "Seoul",
  "address": "Gangnam-gu",
  "hospital_type": "CLINIC",
  "latitude": "37.5000000",
  "longitude": "127.0300000",
  "phone": "02-0000-0000",
  "website": "https://hospital.example.com",
  "description": "피부 시술 전문 병원",
  "business_hours": "09:00-18:00",
  "image_url": "https://cdn.example.com/hospital.jpg",
  "specialties": [
    {
      "hospital_specialty_id": 4,
      "specialty_code": "PIGMENTATION",
      "specialty_name": "색소",
      "is_custom": false
    }
  ],
  "collaboration_count": 6
}
```

### 3.4 추천 객체

```json
{
  "recommendation_id": 101,
  "rank_number": 1,
  "batch_number": 1,
  "hospital": {
    "hospital_id": 3,
    "name": "예시병원",
    "country": "KR",
    "city": "Seoul",
    "address": "Gangnam-gu",
    "hospital_type": "CLINIC",
    "latitude": "37.5000000",
    "longitude": "127.0300000",
    "phone": "02-0000-0000",
    "website": "https://hospital.example.com",
    "description": "피부 시술 전문 병원",
    "business_hours": "09:00-18:00",
    "image_url": "https://cdn.example.com/hospital.jpg",
    "specialties": [],
    "collaboration_count": 6
  },
  "specialty_score": "100.00",
  "distance_score": "90.00",
  "collaboration_score": "80.00",
  "total_score": "93.00",
  "distance_km": "3.21",
  "is_selected": false,
  "created_at": "2026-08-16T12:00:05+09:00"
}
```

점수와 거리는 `DecimalField`이므로 JSON 응답에서 문자열로 직렬화될 수 있다.

---

## 4. 매칭 요청 생성 및 추천 실행

```http
POST /api/matching/requests/
Content-Type: application/json
Authorization: Bearer {access_token}
```

제출 완료된 증상 케이스를 AI로 분석하고 추천 병원을 생성한다. AI 처리는 요청 안에서 동기적으로 실행되므로 응답 시간이 길어질 수 있다.

### 4.1 Path Variable

없음.

### 4.2 Query Parameter

없음.

### 4.3 Request Body

#### 공통 필드

| 필드 | 형식 | 필수 | 기본값 | 설명 |
|---|---|---:|---:|---|
| `symptom_case` | integer | O | - | 본인의 `SUBMITTED` 증상 케이스 ID |
| `specialty_weight` | integer | X | 50 | 전문분야 가중치, 0~100 |
| `distance_weight` | integer | X | 50 | 거리 가중치, 0~100 |
| `collaboration_weight` | integer | X | 50 | 협진 경험 가중치, 0~100 |
| `location_source` | enum | X | `PROFILE` | `PROFILE` 또는 `CUSTOM` |

#### `PROFILE` 요청

```json
{
  "symptom_case": 31,
  "location_source": "PROFILE",
  "specialty_weight": 50,
  "distance_weight": 30,
  "collaboration_weight": 20
}
```

`search_*`는 보내지 않아도 된다. 서버가 프로필 위치를 사용한다.

#### `CUSTOM` 추가 필드

| 필드 | 형식 | 필수 | 설명 |
|---|---|---:|---|
| `search_country` | string, 최대 50자 | O | 검색 국가. 병원 `country`와 정확히 비교 |
| `search_city` | string, 최대 100자 | X | 검색 도시 |
| `search_address` | string, 최대 255자 | X | 검색 주소 |
| `search_latitude` | decimal | O | 위도, 최대 10자리·소수점 7자리 |
| `search_longitude` | decimal | O | 경도, 최대 10자리·소수점 7자리 |

```json
{
  "symptom_case": 31,
  "location_source": "CUSTOM",
  "search_country": "JP",
  "search_city": "Tokyo",
  "search_address": "Shinjuku",
  "search_latitude": "35.6762000",
  "search_longitude": "139.6503000",
  "specialty_weight": 40,
  "distance_weight": 40,
  "collaboration_weight": 20
}
```

### 4.4 처리 흐름

```text
환자 프로필 확인
→ 요청 필드·위치·가중치 검증
→ 증상 케이스 소유권 확인
→ 증상 상태가 SUBMITTED인지 확인
→ HospitalMatchRequest 생성
→ 증상 상태 MATCHING
→ AI 전문분야 분석
→ 병원 점수 계산 및 최대 20개 추천 저장
→ 매칭 요청 상태 COMPLETED
```

AI 처리 실패 시:

```text
매칭 요청 상태 PENDING
증상 케이스 상태 SUBMITTED
HTTP 502 반환
```

### 4.5 성공 응답 `201 Created`

```json
{
  "match_request": {
    "match_request_id": 12,
    "symptom_case": 31,
    "patient_id": 7,
    "required_specialty": "색소",
    "required_specialty_code": "PIGMENTATION",
    "specialty_weight": 50,
    "distance_weight": 30,
    "collaboration_weight": 20,
    "location_source": "PROFILE",
    "search_country": "KR",
    "search_city": "Seoul",
    "search_address": "Gangnam-gu",
    "search_latitude": "37.4979000",
    "search_longitude": "127.0276000",
    "personal_information_provision_agreed": false,
    "information_items_purpose_confirmed": false,
    "medical_consultation_use_agreed": false,
    "withdrawal_right_confirmed": false,
    "agreed_at": null,
    "status": "COMPLETED",
    "created_at": "2026-08-16T12:00:00+09:00",
    "updated_at": "2026-08-16T12:00:05+09:00"
  },
  "recommendations": [
    {
      "recommendation_id": 101,
      "rank_number": 1,
      "batch_number": 1,
      "hospital": {},
      "specialty_score": "100.00",
      "distance_score": "90.00",
      "collaboration_score": "80.00",
      "total_score": "93.00",
      "distance_km": "3.21",
      "is_selected": false,
      "created_at": "2026-08-16T12:00:05+09:00"
    }
  ]
}
```

조건에 맞는 병원이 없으면 `recommendations`는 빈 배열이며 요청 자체는 성공할 수 있다.

### 4.6 오류 응답

#### `400 Bad Request`

- 증상 케이스 상태가 `SUBMITTED`가 아님
- 가중치가 0~100 범위를 벗어남
- 모든 가중치가 0
- `PROFILE`인데 프로필 국가·좌표가 없음
- `CUSTOM`인데 필수 검색 위치가 없음
- 존재하지 않는 증상 케이스 등 serializer 검증 실패

예시:

```json
{
  "search_latitude": ["프로필에 거주지 좌표를 등록해 주세요."],
  "search_longitude": ["프로필에 거주지 좌표를 등록해 주세요."]
}
```

#### `401 Unauthorized`

```json
{
  "detail": "자격 인증데이터가 제공되지 않았습니다."
}
```

#### `403 Forbidden`

- 환자 프로필이 없음
- 다른 환자의 증상 케이스 사용 시도

#### `502 Bad Gateway`

AI 분석 또는 추천 생성 중 오류가 발생한 경우다.

```json
{
  "detail": "병원 추천 분석 중 오류가 발생했습니다.",
  "error": "내부 오류 메시지"
}
```

---

## 5. 매칭 요청 상세 조회

```http
GET /api/matching/requests/{match_request_id}/
Authorization: Bearer {access_token}
```

본인의 매칭 요청 정보를 조회한다. 추천 병원 배열은 포함하지 않는다.

### 5.1 Path Variable

| 변수 | 형식 | 필수 | 설명 |
|---|---|---:|---|
| `match_request_id` | integer | O | 조회할 매칭 요청 PK |

### 5.2 Query Parameter

없음.

### 5.3 Request Body

없음.

### 5.4 성공 응답 `200 OK`

매칭 요청 객체를 반환한다.

```json
{
  "match_request_id": 12,
  "symptom_case": 31,
  "patient_id": 7,
  "required_specialty": "색소",
  "required_specialty_code": "PIGMENTATION",
  "specialty_weight": 50,
  "distance_weight": 30,
  "collaboration_weight": 20,
  "location_source": "PROFILE",
  "search_country": "KR",
  "search_city": "Seoul",
  "search_address": "Gangnam-gu",
  "search_latitude": "37.4979000",
  "search_longitude": "127.0276000",
  "personal_information_provision_agreed": false,
  "information_items_purpose_confirmed": false,
  "medical_consultation_use_agreed": false,
  "withdrawal_right_confirmed": false,
  "agreed_at": null,
  "status": "COMPLETED",
  "created_at": "2026-08-16T12:00:00+09:00",
  "updated_at": "2026-08-16T12:00:05+09:00"
}
```

### 5.5 오류 응답

- `401 Unauthorized`: 인증 실패
- `403 Forbidden`: 환자 프로필 없음
- `404 Not Found`: 매칭 요청이 없거나 본인의 요청이 아님

```json
{
  "detail": "매칭 요청을 찾을 수 없습니다."
}
```

---

## 6. 추천 병원 목록 조회

```http
GET /api/matching/requests/{match_request_id}/recommendations/
Authorization: Bearer {access_token}
```

특정 매칭 요청에 생성된 추천 병원을 순위순으로 조회한다.

### 6.1 Path Variable

| 변수 | 형식 | 필수 | 설명 |
|---|---|---:|---|
| `match_request_id` | integer | O | 추천 결과를 조회할 매칭 요청 PK |

### 6.2 Query Parameter

없음. 현재 `batch_number`, 순위, 점수 등에 대한 서버 필터나 페이지네이션은 제공하지 않는다.

### 6.3 Request Body

없음.

### 6.4 성공 응답 `200 OK`

```json
{
  "match_request_id": 12,
  "required_specialty": "색소",
  "required_specialty_code": "PIGMENTATION",
  "recommendations": [
    {
      "recommendation_id": 101,
      "rank_number": 1,
      "batch_number": 1,
      "hospital": {
        "hospital_id": 3,
        "name": "예시병원",
        "country": "KR",
        "city": "Seoul",
        "address": "Gangnam-gu",
        "hospital_type": "CLINIC",
        "latitude": "37.5000000",
        "longitude": "127.0300000",
        "phone": "02-0000-0000",
        "website": "https://hospital.example.com",
        "description": "피부 시술 전문 병원",
        "business_hours": "09:00-18:00",
        "image_url": "https://cdn.example.com/hospital.jpg",
        "specialties": [
          {
            "hospital_specialty_id": 4,
            "specialty_code": "PIGMENTATION",
            "specialty_name": "색소",
            "is_custom": false
          }
        ],
        "collaboration_count": 6
      },
      "specialty_score": "100.00",
      "distance_score": "90.00",
      "collaboration_score": "80.00",
      "total_score": "93.00",
      "distance_km": "3.21",
      "is_selected": false,
      "created_at": "2026-08-16T12:00:05+09:00"
    }
  ]
}
```

### 6.5 오류 응답

- `401 Unauthorized`: 인증 실패
- `403 Forbidden`: 환자 프로필 없음
- `404 Not Found`: 매칭 요청이 없거나 본인의 요청이 아님

---

## 7. 추천 병원 선택

```http
POST /api/matching/recommendations/{recommendation_id}/select/
Authorization: Bearer {access_token}
```

추천 결과 중 한 병원을 선택한다. 동일 매칭 요청의 기존 선택을 모두 해제한 뒤 지정한 추천만 선택한다.

### 7.1 Path Variable

| 변수 | 형식 | 필수 | 설명 |
|---|---|---:|---|
| `recommendation_id` | integer | O | 선택할 추천 PK |

### 7.2 Query Parameter

없음.

### 7.3 Request Body

없음.

### 7.4 처리 결과

- 해당 매칭 요청의 모든 추천 `is_selected=false`
- 선택 추천 `is_selected=true`
- 매칭 요청 상태 `SELECTED`
- 기존 네 가지 매칭 동의값을 모두 `false`로 초기화
- `agreed_at=null`로 초기화
- 증상 케이스 상태 `HOSPITAL_SELECTED`

병원을 다시 선택하면 이전 병원에 대한 동의 정보도 초기화된다.

### 7.5 성공 응답 `200 OK`

```json
{
  "message": "협진 상대 병원이 선택되었습니다.",
  "match_request_id": 12,
  "symptom_case_id": 31,
  "recommendation_id": 101,
  "partner_hospital_id": 3,
  "partner_hospital_user_id": 44,
  "partner_hospital_name": "예시병원"
}
```

`partner_hospital_id`는 `HospitalProfile` PK이고 `partner_hospital_user_id`는 병원 계정의 `User` PK다.

### 7.6 오류 응답

- `401 Unauthorized`: 인증 실패
- `403 Forbidden`: 환자 프로필이 없거나 다른 환자의 추천 선택 시도
- `404 Not Found`: 추천 ID가 존재하지 않음

```json
{
  "detail": "추천 병원을 찾을 수 없습니다."
}
```

### 7.7 현재 구현상 참고

현재 view에서는 선택 전 매칭 요청 상태가 반드시 `COMPLETED`인지 별도로 검사하지 않는다. 존재하며 본인 소유인 추천이면 선택 로직이 수행된다.

---

## 8. 선택 병원 매칭 동의

```http
PATCH /api/matching/requests/{match_request_id}/consent/
Content-Type: application/json
Authorization: Bearer {access_token}
```

병원 선택 후 매칭에 필요한 네 가지 필수 동의를 저장한다.

### 8.1 Path Variable

| 변수 | 형식 | 필수 | 설명 |
|---|---|---:|---|
| `match_request_id` | integer | O | 동의할 매칭 요청 PK |

### 8.2 Query Parameter

없음.

### 8.3 Request Body

네 필드 모두 `true`여야 한다.

| 필드 | 형식 | 필수 | 허용값 | 설명 |
|---|---|---:|---|---|
| `personal_information_provision_agreed` | boolean | O | `true` | 개인정보 제공 동의 |
| `information_items_purpose_confirmed` | boolean | O | `true` | 제공 정보 항목과 목적 확인 |
| `medical_consultation_use_agreed` | boolean | O | `true` | 의료 상담 활용 동의 |
| `withdrawal_right_confirmed` | boolean | O | `true` | 동의 철회 권리 확인 |

```json
{
  "personal_information_provision_agreed": true,
  "information_items_purpose_confirmed": true,
  "medical_consultation_use_agreed": true,
  "withdrawal_right_confirmed": true
}
```

### 8.4 선행 조건

- 본인의 매칭 요청이어야 한다.
- 매칭 요청 상태가 `SELECTED`여야 한다.
- 네 가지 동의가 모두 `true`여야 한다.

### 8.5 성공 처리

- 네 가지 동의값 저장
- `agreed_at`을 현재 시각으로 저장
- 매칭 요청 상태는 `SELECTED`로 유지

### 8.6 성공 응답 `200 OK`

전체 매칭 요청 객체를 반환한다.

```json
{
  "match_request_id": 12,
  "symptom_case": 31,
  "patient_id": 7,
  "required_specialty": "색소",
  "required_specialty_code": "PIGMENTATION",
  "specialty_weight": 50,
  "distance_weight": 30,
  "collaboration_weight": 20,
  "location_source": "PROFILE",
  "search_country": "KR",
  "search_city": "Seoul",
  "search_address": "Gangnam-gu",
  "search_latitude": "37.4979000",
  "search_longitude": "127.0276000",
  "personal_information_provision_agreed": true,
  "information_items_purpose_confirmed": true,
  "medical_consultation_use_agreed": true,
  "withdrawal_right_confirmed": true,
  "agreed_at": "2026-08-16T12:10:00+09:00",
  "status": "SELECTED",
  "created_at": "2026-08-16T12:00:00+09:00",
  "updated_at": "2026-08-16T12:10:00+09:00"
}
```

### 8.7 오류 응답

#### `400 Bad Request`

병원을 선택하지 않았거나 필수 동의가 하나라도 `false`·누락인 경우다.

```json
{
  "non_field_errors": [
    "병원 매칭을 위한 필수 동의가 필요합니다."
  ]
}
```

#### 기타 오류

- `401 Unauthorized`: 인증 실패
- `403 Forbidden`: 환자 프로필 없음
- `404 Not Found`: 매칭 요청이 없거나 본인의 요청이 아님

---

## 9. 전체 상태 전이

```text
PatientSymptomCase.SUBMITTED
  │
  │ POST /api/matching/requests/
  ▼
PatientSymptomCase.MATCHING
HospitalMatchRequest.PENDING → ANALYZING
  │
  ├─ 성공
  │    HospitalMatchRequest.COMPLETED
  │
  └─ 실패
       HospitalMatchRequest.PENDING
       PatientSymptomCase.SUBMITTED

HospitalMatchRequest.COMPLETED
  │
  │ POST /api/matching/recommendations/{id}/select/
  ▼
HospitalMatchRequest.SELECTED
PatientSymptomCase.HOSPITAL_SELECTED
동의값 전체 초기화
  │
  │ PATCH /api/matching/requests/{id}/consent/
  ▼
동의값 전체 true
agreed_at 기록
```

---

## 10. HTTP 상태 코드 요약

| 상태 코드 | 사용 상황 |
|---:|---|
| `200 OK` | 상세·추천 조회, 병원 선택, 매칭 동의 성공 |
| `201 Created` | 매칭 요청 및 추천 생성 성공 |
| `400 Bad Request` | 상태·필드·위치·가중치·동의 검증 실패 |
| `401 Unauthorized` | 인증 정보 없음 또는 유효하지 않음 |
| `403 Forbidden` | 환자 프로필 없음 또는 다른 환자 데이터 접근 |
| `404 Not Found` | 본인 소유의 매칭 요청이나 추천을 찾을 수 없음 |
| `502 Bad Gateway` | AI 분석 또는 추천 생성 실패 |

---

## 11. 구현되지 않은 기능

- 매칭 요청 목록 조회 API
- 매칭 요청 취소 API
- 추천 결과 Query Parameter 필터·정렬·페이지네이션
- 추천 단건 조회 API
- Matching 앱 내부의 병원 연결 요청 API

현재 실제 병원 연결과 협진 흐름은 `cases` 앱의 케이스 전송 및 협진 요청 흐름에서 처리한다.

---

## 12. 클라이언트 구현 체크리스트

1. 증상 케이스를 먼저 `SUBMITTED` 상태로 만든다.
2. `PROFILE` 사용 전 환자 프로필의 국가와 좌표 존재 여부를 확인한다.
3. `CUSTOM`이면 국가·위도·경도를 반드시 전송한다.
4. 매칭 생성 API는 AI를 동기 호출하므로 로딩·재시도 UI를 제공한다.
5. 추천 응답의 `specialties`는 문자열 배열이 아니라 객체 배열이다.
6. `partner_hospital_id`와 `partner_hospital_user_id`를 구분한다.
7. 병원 선택 후 네 가지 매칭 동의를 별도 호출한다.
8. 병원을 다시 선택하면 기존 동의가 모두 초기화된다는 점을 반영한다.
