# 검증 기록

2026-10-13 UTC. 로컬 실행 결과와 GitHub/외부 배포 상태를 구분합니다. 기계 기록은 [verification-results.json](verification-results.json)에 있습니다.

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
| GitHub main 푸시 | **GitHub HTTP 403으로 차단** |
| GitHub Actions 실행 | **미실행: 원격 푸시가 차단됨** |
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

## Git 보존과 원격 차단

로컬 저장소는 `main`, origin은 `https://github.com/yongseung716/Running-coach.git`입니다. 초기 commit `94c33c6`에 기존 전체 소스·테스트·CI와 package-lock.json을 보존했습니다. UI 수정과 최신 검증 문서는 후속 commit에 보존합니다. .venv, node_modules, 실제 .env 변형, data, 인증 서명 키, .pem/.key/.p12/.pfx는 제외합니다. 빈 값의 .env.example 템플릿은 실행 설정 안내용으로 유지합니다.

정상 인증된 GitHub CLI 조회와 네트워크 설치는 성공했지만, `git push -u origin main`은 provider의 HTTP 403으로 거절되었습니다. 자동 승인 검토가 거절한 것이 아니라 GitHub가 쓰기를 차단한 결과입니다. 따라서 원격 commit·Actions run URL은 아직 존재하지 않습니다. 사용자가 공유한 GitHub 설정 화면에는 `No installed GitHub Apps`가 표시되어 연결용 App 설치가 필요함을 확인했습니다. GitHub 모바일 앱 설치와 별도로 Codex의 GitHub 연결에서 저장소를 선택·승인해야 합니다.

## GitHub Actions 준비

`.github/workflows/ci.yml`에 push/pull_request/workflow_dispatch 트리거를 구성했습니다. `regression` job은 기존 29개를 15/7/7로 분리해서 재실행합니다. `verify` job은 전체 Python 39개, npm ci, TypeScript, RLS, build, 모바일·데스크톱 browser test를 실행합니다. 이 workflow는 로컬 commit에 포함되었고 원격 업로드 후 실제 실행 결과를 확인해야 합니다. Git 전체 이력을 보존한 bundle의 사용법은 [GITHUB-PUBLISH.md](GITHUB-PUBLISH.md)에 있습니다.
