# backend
이화여대 멋쟁이사자처럼 중앙해커톤 2팀 백엔드

## 업로드 파일 저장소

로컬 개발 환경에서는 파일을 `media/`에 저장합니다. Render에서는
재배포 후에도 파일을 유지하도록 Cloudinary 설정이 필수입니다.

다음 두 방식 중 하나로 환경변수를 등록합니다.

- `CLOUDINARY_URL=cloudinary://<api_key>:<api_secret>@<cloud_name>`
- `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`

Render에서 이 설정이 누락되면 휘발성 로컬 디스크로 저장하지 않고 배포 시작이
실패합니다.
