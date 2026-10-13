# API v1

OpenAPI: API `/docs`, 기계 명세 `/openapi.json`. Frontend는 `/api` prefix를 사용하며 proxy에서 제거된다. JSON 오류 `{detail: string}`. 인증 실패 401, 권한 부족 403, 비공개 리소스 미존재 404, 충돌 409, 입력 422, 제한 413/429. IDs는 UUID. 쿠키 인증 + mutation Origin 검사; 자동화는 Bearer JWT 사용.

| Method | Path | 의미 |
|---|---|---|
| POST | /auth/signup | email/password/display_name. 운영은 이메일 확인 가능 |
| POST | /auth/login, /auth/refresh, /auth/logout | HttpOnly access/refresh 세션 |
| GET/PATCH | /profile | 본인 목표/설정 |
| GET/POST | /crews | 본인 크루/생성 |
| GET | /crews/{id} | 활성 회원·본인 가입 상태 |
| POST | /crews/{id}/invites | owner/admin 초대 코드 발급 (7일) |
| POST | /crews/join | code로 pending 가입 요청 |
| PATCH | /crews/{id}/members/{user_id} | status 또는 role (권한/owner 보호) |
| PATCH | /crews/{id}/consent | share_summary 본인 설정 |
| POST | /crews/{id}/transfer | 소유권 양도 |
| DELETE | /crews/{id}/membership | 탈퇴 |
| GET | /crews/{id}/summary | 동의 기반 28일 집계, 원본 없음 |
| POST | /runs | multipart file. 202 queued 또는 중복 기존 기록 |
| GET | /runs | 본인 최근 100개, cursor 페이지 |
| GET/DELETE | /runs/{id} | 본인 분석/파일+분석 삭제 |
| GET | /runs/{id}/file | 본인 원본 GPX 다운로드 |
| GET | /dashboard | 본인 28일/주간 요약 |
| GET/POST | /plans | 목록/현재 주 계획 생성(동일 주 idempotent) |
| PUT/DELETE | /plans/{id}/days/{index}/completion | 완료/취소, 본인 run_id 연결 가능 |
| GET | /account/export | 본인 프로필·기록·계획·원본 ZIP |
| DELETE | /account | confirm=DELETE 및 최근 로그인 필수, 소유 크루 양도 후 삭제 |
| GET | /health | public readiness(설정된 모드/엔진 버전) |

내보내기와 목록은 private no-store 응답. ZIP 원본 이름은 UUID로 고정하고 사용자 파일명을 경로에 쓰지 않는다. 파일 읽기는 DB 소유권 검사 후 서버 Storage에서 수행한다. 상태는 UI에서 polling하여 보여주며 worker 실행이 필수다.
