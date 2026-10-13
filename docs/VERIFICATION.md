# 검증 기록

## 무료 베타 실행 구성 추가 검증 (2026-10-13)

추가 구성의 원격 CI도 성공했습니다: [GitHub Actions 38347722161](https://github.com/yongseung716/Running-coach/actions/runs/38347722161). 검증한 코드 commit은 `f14bddf473b5c918236dfc1f563408970762cfbb`이며 기존 29개 회귀 job과 전체 verify job 모두 성공했습니다. 전체 job에서 Python 39개, 실제 프로세스 smoke test, TypeScript, PostgreSQL RLS, Next 빌드와 브라우저 테스트를 재실행했습니다. 결과 기록 후속 commit은 문서만 변경합니다.

`python -m coach.serve`로 API와 분석 워커를 한 호스트의 별도 프로세스로 실행하는 선택지를 추가했습니다. 로컬에서도 같은 런처를 사용합니다. 기존 Python 39개(기존 회귀 29개 포함)와 실제 업로드/분석을 포함한 모바일·데스크톱 브라우저 4개를 재실행하여 모두 통과했습니다. Linux의 실제 프로세스 smoke test는 호스트가 지정한 PORT, 두 프로세스 기동, SIGTERM 종료 후 자식 프로세스 정리, 워커 강제 종료 시 API도 중단하고 실패 종료하는 동작을 모두 통과했습니다. 이 smoke test는 GitHub Actions에도 추가했습니다.

Render Free는 절전 중 분석이 멈추는 베타용 구성입니다. Supabase DB/비공개 Storage에 데이터를 저장하며 다음 기동 때 작업을 재개합니다. Render에 실제 배포하거나 절전/재접속을 실서비스로 검증한 상태는 아닙니다. 설정과 제한은 [RENDER-FREE-BETA.md](RENDER-FREE-BETA.md)를 참조하세요. 아래 원격 CI 기록은 이전 검증 코드의 이력을 보존합니다.

2026-10-13 UTC. 로컬 및 GitHub Actions에서 검증을 완료했습니다. 실제 Supabase/Vercel 운영 배포와는 구분합니다. 기계 기록은 [verification-results.json](verification-results.json)에 있습니다.

| 검사 | 실제 결과 |
|---|---|
| 기존 GPX 분석 회귀 테스트 | 15개 통과 |
| 기존 규칙 코칭 회귀 테스트 | 7개 통과 |
| 기존 JWT·비밀번호·저장소 보안 회귀 테스트 | 7개 통과 |
| API 통합 테스트 | 10개 통과 |
| Python 전체 | **39개 통과 (기존 29개 포함)** |
| PostgreSQL RLS (PGlite) | **24개 assertion 통과** |
| TypeScript | 통과 |
| Next.js 최종 소스 빌드 | 통과 (15.5.27) |
| 모바일·데스크톱 Playwright | **4개 통과** |
| GitHub main 푸시 | **성공** |
| GitHub Actions 실행 | **두 job 모두 성공** |
| 실제 Supabase Auth/Storage·Vercel 배포 | 미실행: 외부 프로젝트 설정 필요 |

## 실제 동작 확인

브라우저 테스트는 테스트 계정을 가입하고 실제 GPX fixture를 업로드하여 worker의 분석 완료를 기다립니다. 계획 생성·완료 기록, 크루 생성·초대·공유 동의, 프로필 저장, ZIP 내보내기, 로그아웃·재로그인, 원본/분석 삭제를 모바일과 데스크톱에서 확인했습니다. 잘못된 GPX는 실제 API 검증 오류를 표시합니다. API 테스트는 계정 삭제·실제 파일 삭제, 교차 사용자 조회/원본/삭제 차단, owner/admin/member 권한, 동의 철회, lease 복구와 3회 재시도도 확인합니다.

fixture는 합성 테스트 자료이며 기본 계정에 자동 삽입되지 않습니다. 고정된 과거 날짜라 최근 28일 대시보드/처방에서 제외되는 조건도 검증했습니다. PGlite는 실제 PostgreSQL migration/RLS 쿼리를 실행하지만 Supabase 플랫폼 Auth·Storage 실서비스 smoke test를 대신하지 않습니다.

## 발견·수정 및 재검증

- 시간대 없는 datetime, 빈 `<time/>`, XML 주석/processing instruction 처리 오류를 수정하고 알고리즘 회귀 테스트를 통과했습니다. 범위 밖 고도는 결측과 경고로 처리합니다.
- 훈련량 반올림이 5% 상한을 넘지 않도록 내림 계산과 마지막 일자 잔여량 배분을 검증했습니다.
- 모바일 계획 완료 폼이 가로 폭을 넘어서 하단 메뉴 클릭을 방해하던 문제를 실제 Playwright trace에서 확인하고 flex 너비를 수정했습니다.
- 비동기 공유 동의 checkbox가 응답 전 이전 값으로 되돌아가던 문제를 즉시 상태 반영 및 요청 실패 시 복원으로 수정했습니다.
- 가입 후 로그아웃에서 가입 폼이 남는 상태 오류를 수정했습니다.
- Next의 route announcer와 앱 오류 알림을 구분하도록 테스트 locator를 수정했습니다.
- 깨끗한 checkout에서도 route 타입을 생성하도록 typecheck에 `next typegen`을 추가했습니다.
- 수정 후 모바일·데스크톱 4개 브라우저 테스트 및 최종 Next.js 빌드를 재실행하여 통과했습니다.

## Git 보존과 연결 복구

로컬 저장소는 `main`, origin은 `https://github.com/yongseung716/Running-coach.git`입니다. 초기 commit `94c33c6`에 기존 전체 소스·테스트·CI와 package-lock.json을 보존했습니다. UI 수정과 최신 검증 문서는 후속 commit에 보존합니다. .venv, node_modules, 실제 .env 변형, data, 인증 서명 키, .pem/.key/.p12/.pfx는 제외합니다. 빈 값의 .env.example 템플릿은 실행 설정 안내용으로 유지합니다.

초기에는 GitHub 계정의 push/admin 권한 조회는 성공했지만 연결용 App 설치가 0개여서 실제 push가 HTTP 403으로 거절됐습니다. 사용자가 `https://github.com/apps/chatgpt-codex-connector/installations/new`에서 저장소 소유 계정에 ChatGPT Codex Connector를 설치한 후 installation 및 대상 저장소 접근을 확인했고, 동일한 `git push -u origin main`이 성공했습니다. 원인은 계정 소유권 부족이 아니라 연결용 App 설치가 완료되지 않은 상태였습니다.

## GitHub Actions 실제 결과

`.github/workflows/ci.yml`에 push/pull_request/workflow_dispatch 트리거를 구성했습니다. `regression` job은 기존 29개를 15/7/7로 분리해서 재실행합니다. `verify` job은 전체 Python 39개, npm ci, TypeScript, RLS, build, 모바일·데스크톱 browser test를 실행합니다. 이 workflow를 main에 푸시한 후 원격에서 두 job 모두 성공했습니다. Git 전체 이력을 보존한 bundle의 사용법은 [GITHUB-PUBLISH.md](GITHUB-PUBLISH.md)에 있습니다.

실제 성공 실행: [https://github.com/yongseung716/Running-coach/actions/runs/38343946786](https://github.com/yongseung716/Running-coach/actions/runs/38343946786). 검증한 코드 commit: `84a2c6fc71169ead518b2c842036d4b4c7cc535e`. CI의 원본 요약은 [github-actions-results.json](github-actions-results.json)에 보존합니다. 회귀 job은 26초, 전체 verify job은 1분 56초에 성공했으며 실패 수정이 필요한 원격 CI 오류는 없었습니다. 이 결과를 기록하는 마지막 commit은 문서만 변경하며 이미 통과한 코드에는 변경이 없습니다.
