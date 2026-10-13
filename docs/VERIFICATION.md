# 검증 기록

작성: 2026-10-13 UTC. 아래 결과는 이 실행 환경에서 실제 실행한 검사와, 작성했지만 실행하지 못한 검사를 구분합니다.

| 검사 | 실제 결과 |
|---|---|
| GPX 엔진 unittest | 15개 통과 |
| 규칙 코칭 unittest | 7개 통과 |
| JWT·비밀번호·저장소 보안 unittest | 7개 통과 |
| Python 전체 소스 compileall | 통과 |
| service worker / RLS runner JS 구문 | node --check 통과 |
| API 통합 테스트 10개 | 실행 미완료: sqlalchemy가 미설치되어 import 실패 |
| PostgreSQL RLS (PGlite) | 실행 미완료: npm dependencies 미설치 |
| TypeScript typecheck / Next build | 실행 미완료: npm dependencies 미설치 |
| 모바일/데스크톱 Playwright | 실행 미완료: Next/Python 의존성 미설치 |
| Docker build / 실제 Supabase / Vercel | 미실행: 플랫폼 설정과 권한 필요 |

기본 실행에서 패키지 설치가 `Operation not permitted`로 실패했습니다. 사용자의 네트워크 설치 승인 후에도 추가 권한·샌드박스 밖 실행 요청이 대기 후 중단되어 패키지가 설치되지 않았습니다. 프록시 연결을 짧은 timeout으로 진단한 결과도 연결 실패였습니다. 지원되는 managed Docker 소켓 또한 `connect: operation not permitted`여서 실행되지 않았습니다. daemon은 실행 중이며 task UID는 1000이라 daemon 재시작은 하지 않았습니다.

GitHub Actions 원격 검증 대안을 준비했습니다. 사용자가 생성한 `yongseung716/Running-couch`는 metadata 조회에 성공했고 비어 있는 저장소임을 확인했습니다. 그러나 README 초기 업로드가 GitHub API **403 Resource not accessible by integration**으로 거절되어 GitHub 연결의 저장소 쓰기 접근 설정이 필요합니다. 초기 커밋·브랜치·PR·CI 실행은 아직 생성되지 않았습니다. 연결된 계정은 저장소 소유 계정과 일치하지만, 계정 소유권과 integration token 권한은 별개입니다. 저장소 목록은 여전히 비어 있어 설치의 Repository access 설정도 확인해야 합니다.

접근 설정이 완료되면 준비된 workflow를 별도 브랜치/초안 PR에 넣고 실제 CI 결과를 확인할 수 있습니다. 이 상태에서 전체 앱의 정상 동작이나 배포 성공을 확인했다고 주장하지 않습니다. Supabase/Auth/Storage/Vercel 계정이나 키는 구성되어 있지 않습니다.

`python scripts/verify.py`의 실제 결과는 [verification-results.json](verification-results.json)에 있습니다. **29개 테스트 통과**, 의존성이 없는 나머지 검사는 `blocked`, 전체 검증 종료 코드는 **2**입니다(성공 코드 0이 아님).

## 실제로 발견·수정한 오류

시간대 없는 datetime을 parsing할 때 naive 객체가 남아 timezone-aware 시각과 뺄셈하는 오류를 unittest가 검출했습니다. timezone 누락을 결측으로 처리하도록 수정하여 회귀 테스트를 통과했습니다. 주간 훈련량 반올림으로 5% 상한을 넘지 않도록 내림 계산·마지막 훈련일 잔여량 분배도 검증했습니다.

추가 점검에서 빈 `<time/>`의 None 처리, lxml 주석/processing instruction 처리도 보강하여 실제 unittest를 통과했습니다. 비현실적인 고도는 결측과 경고로 처리합니다. JWT의 변조 서명·unsigned token·만료·다른 issuer/audience·미래 발급·잘못된 subject, salt가 다른 비밀번호 hash, 저장소 경로 침범과 실제 원본 삭제도 검증했습니다. 분석 엔진 버전은 1.0.1입니다.

## 설치 후 필수 검사

README의 설치/전체 unittest/typecheck/RLS/build/Playwright 명령을 실행하고 이 표를 실제 결과로 갱신합니다. 특히 SQLAlchemy transaction/RLS role 강등, durable worker 3회 retry, Supabase Storage remove API, 이메일 확인/JWKS/refresh/최근 인증 제한, 계정 삭제와 실제 저장소 제거, Vercel 동일 출처 proxy cookie/10 MiB 업로드는 실제 플랫폼에서 확인해야 합니다.

브라우저 테스트는 합성 fixture를 명시적으로 업로드해 실제 분석 엔진/worker를 실행합니다. mock 수치를 데이터처럼 보여주지 않으며, 기본 UI 계정에는 분석 기록이 없습니다. fixture가 과거 날짜라 최근 대시보드/처방에 들어가지 않는 조건도 API 테스트에 포함했습니다.

이 저장소는 베타용 구현본이며, 실행되지 않은 통합/보안 검증을 완료하기 전 실제 개인정보를 수집하는 운영 배포를 시작하지 마세요.

공식 OpenAI 문서 확인 후 정정: 일반 ChatGPT GitHub 연결은 읽기 전용입니다. 저장소 접근 범위 추가만으로 코드 push 권한이 생기지는 않습니다. 코드 업로드에는 Codex 저장소/환경 연결이 필요하며, 현재 403의 해결 여부는 그 연결 상태를 다시 확인해야 합니다. 화면 안내는 [github-guide/README.md](github-guide/README.md)에 있습니다.
