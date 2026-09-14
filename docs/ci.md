# 자동화 테스트와 CI

GitHub Actions가 모든 브랜치의 push와 pull request에서 Django 검사와 기존 테스트를 실행합니다.
Actions 탭에서 수동 실행도 가능합니다. 배포는 수행하지 않습니다.

## 실행 순서

1. Python 3.11과 requirements-ci.txt의 의존성 설치
2. Django 설정 검사: python manage.py check
3. 모델 변경에 필요한 마이그레이션 누락 검사
4. 전체 테스트 실행 및 줄·분기 커버리지 측정
5. 실행 요약에 커버리지 표시, HTML/XML 보고서를 14일간 보관

검사 또는 테스트가 실패하면 CI가 실패합니다. 실패한 테스트 실행도 가능한 경우 커버리지 보고서를 남깁니다.
CI 설정과 실제 GitHub 실행 성공 여부는 별개이므로 첫 push 후 Actions 결과를 확인하세요.

## 로컬 실행 (PowerShell)

가상환경이 활성화된 상태에서:

~~~powershell
python -m pip install -r requirements-ci.txt
python manage.py check --settings=config.settings_test
python manage.py makemigrations --check --dry-run --settings=config.settings_test
python -m coverage run manage.py test --settings=config.settings_test --noinput --verbosity 2
python -m coverage report
python -m coverage html
~~~

htmlcov/index.html에서 파일별로 테스트가 실행하지 않은 코드를 확인할 수 있습니다.
테스트 설정은 .env를 읽지 않고 메모리 SQLite DB와 메모리 파일 저장소를 사용합니다.
실제 외부 API 호출이 필요한 코드는 테스트에서 mock으로 대체해야 합니다.
이 설정은 배포용이 아니며 운영 PostgreSQL의 동시성·잠금 동작을 검증하지는 않습니다.

## 개선 지표 기록

| 지표 | 확인 위치 |
| --- | --- |
| 테스트 수와 실패 수 | Run tests with coverage 로그 |
| 줄·분기 커버리지 | 실행 Summary 및 coverage-report 아티팩트 |
| 전체 CI 실행 시간 | Actions 실행 화면 |

첫 성공 실행을 기준선으로 삼고, 변경 전후의 커밋과 함께 수치를 기록하세요.
커버리지 하한은 아직 강제하지 않습니다. 기준선을 확인한 뒤 .coveragerc의 [report]에
fail_under 값을 추가해 최소 기준을 설정할 수 있습니다.
커버리지가 높아도 모든 오류를 검증했다는 뜻은 아닙니다.

## GitHub에서 사용하기

변경 파일을 커밋하고 GitHub에 push하면 자동 실행됩니다.
PR의 Checks 또는 저장소 Actions 탭에서 결과를 확인하세요.
병합까지 막으려면 저장소 Ruleset/브랜치 보호에서
Django checks and tests를 필수 상태 검사로 지정해야 합니다. 이 저장소 설정은 별도입니다.

구성 참고: [GitHub 공식 Python CI 안내](https://docs.github.com/en/actions/tutorials/build-and-test-code/python)
## 초기 로컬 측정 결과

2026-09-14, Windows / Python 3.11.9 / 메모리 SQLite 기준:

- Django 설정 검사: 통과
- 마이그레이션 누락 검사: 통과
- 기존 테스트: 150개 통과, 실패 0개
- 테스트 실행 시간: 9.011초 (설치 및 DB 준비 시간 제외)
- 분기 포함 전체 커버리지: 82.34%

커버리지 측정 범위는 accounts, cases, matching, selfsymptoms이며 테스트 코드와
마이그레이션은 제외합니다. GitHub CI 실행 시간과 결과는 첫 push 후 별도로 기록하세요.
