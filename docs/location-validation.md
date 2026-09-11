# 회원가입 위치 필드와 숫자 검증 (#75)

## 프론트 변경
| API | 국가 필드(필수) | 좌표 필드(선택) |
| --- | --- | --- |
| POST /accounts/signup/patient/ | residence_country | latitude, longitude |
| POST /accounts/signup/hospital/ | country | latitude, longitude |

국가는 KR, JP, US, CN 등 ISO alpha-2 코드입니다. 기존 국가명 별칭도 정규화됩니다.
환자 residence_country는 새 필수값이므로 프론트와 배포 시점을 맞춥니다.
병원 country는 기존부터 필수입니다. 언어 preferred_language와 국가 코드는 별개입니다.
기존 가입 필수 항목은 그대로 유지합니다.

기존 환자 가입 본문에 추가할 항목:
```json
{"residence_country": "KR", "latitude": 37.5665, "longitude": 126.978}
```
기존 병원 가입 본문에 추가할 항목:
```json
{"country": "JP", "latitude": 35.6762, "longitude": 139.6503}
```

좌표는 주소에서 자동 계산하지 않습니다. 프론트가 전달한 위치를 프로필에 저장합니다.
가입 응답에는 위치 필드를 포함하지 않으며, 가입 후 각 프로필 GET에서 확인합니다.

## 좌표 검증
- 위도 -90~90, 경도 -180~180, 전체 10자리/소수 최대 7자리.
- 음수와 0 허용. 비숫자, 빈 문자열, NaN, Infinity 거절.
- 가입/프로필은 좌표 두 값 모두 생략 또는 모두 null 허용. 한쪽만 저장할 수 없습니다.
- 프로필 PATCH는 기존 값과 합쳐 검증합니다. 좌표 삭제는 둘 다 null로 요청합니다.
- 매칭은 search_latitude/search_longitude를 사용하고 두 값이 필수입니다.
- PROFILE 매칭은 환자 프로필에서 가져온 좌표도 재검증합니다.
- 입력 오류는 해당 필드명을 포함한 400 응답입니다.

## 추천 숫자 검증
- 가중치 각각 0~100 정수, 기본값 각각 50. 모두 0은 거절.
- 가중치 합계는 100일 필요가 없습니다.
- 전문분야/거리/협진/총점은 0~100.
- 거리 0~99999999.99 km, 계산 불가 시 null 허용.
- 순위/배치 번호 1~32767, 협진 횟수 0~2147483647 정수.
- 내부 계산 결과는 저장 전에 검증하며 잘못된 사용자 입력과 구분합니다.
- 추천 재생성 실패 시 트랜잭션으로 기존 결과를 보존합니다.
- 병원 목록/상세의 누락되거나 잘못된 저장 좌표는 거리 null로 처리합니다.
- 병원 선택은 환자 좌표 필수(400). 잘못된 병원 저장 좌표는 서버 오류입니다.
  병원 좌표가 둘 다 미등록이면 선택 가능하며 거리는 null입니다.

## migration
- accounts.0014: 기존 좌표·가중치·추천 숫자를 읽어 검사.
- accounts.0015 및 matching.0008: validator 및 DB CHECK 제약 추가.
- 잘못된 기존 값이 있으면 모델/PK/필드를 최대 20건 표시하고 중단합니다.
  임의로 위치를 변경하거나 기존 추천 결과를 삭제하지 않습니다.
- 해당 레코드를 확인·정정한 후 python manage.py migrate를 다시 실행합니다.
- DB 제약은 범위와 좌표 쌍을 보장하고, API는 입력 정밀도도 검증합니다.
- 운영 적용 전 DB 백업 및 쓰기 요청 중단 후 새 코드와 함께 배포합니다.

## 테스트
python manage.py test accounts.test_coordinates matching.test_numeric_validation
python manage.py test accounts matching cases selfsymptoms
python manage.py makemigrations --check --dry-run
