# PACE · Running Coach PWA

모바일 우선 러닝 분석·규칙 코칭. Next.js / TypeScript / Tailwind, FastAPI, Supabase 운영 어댑터. 기본 데이터는 비어 있으며, 수치는 업로드한 실제 GPX에서 계산합니다. 운영 모드의 Supabase 키와 외부 배포는 별도 설정이 필요합니다.

## 로컬 실행

Node 22+, Python 3.12+ 필요. 모든 명령은 저장소 루트 기준입니다.

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e 'apps/api[test]'
npm install
cp apps/api/.env.example apps/api/.env
cp apps/web/.env.example apps/web/.env.local
python scripts/serve-api.py
```

별도 터미널:

```bash
npm run dev
```

http://localhost:3000 에서 가입 후 GPX 업로드. API http://localhost:8000/docs. `serve-api.py`는 API와 지속성 있는 분석 worker를 함께 실행합니다. SQLite/원본 GPX/개발 서명 키는 `apps/api/data`에 저장됩니다. 동일 경로를 유지하면 재시작 후에도 계정과 기록이 남습니다. 설치 권한/네트워크가 필요하며 미설치 시 실행할 수 없습니다. `.env`와 data는 Git에 넣지 않습니다.

샘플은 [samples/README.md](samples/README.md) 참조. 고정된 과거 날짜의 합성 fixture라 최근 28일 집계/처방에는 포함되지 않습니다.

## 자동 검증

`python scripts/verify.py`는 가능한 검사를 각각 실행하고 미설치 검사를 `blocked`로 구분하여 `docs/verification-results.json`에 저장합니다. 전체 검증이 통과한 경우에만 종료 코드 0을 반환합니다.

```bash
. .venv/bin/activate
python -m unittest discover -s apps/api/tests -v
npm run typecheck
npm run test:rls
npm run build
cd apps/web
npx playwright install chromium
cd ../..
npm run test:web
```

알고리즘 테스트만 독립 실행하려면 `PYTHONPATH=apps/api python -m unittest discover -s apps/api/tests -p 'test_analysis.py' -v` 및 `test_coaching.py`를 실행합니다. `test:rls`는 PostgreSQL WASM(PGlite)에서 실제 migration과 권한 쿼리를 실행합니다. Supabase 호스팅/Auth/Storage까지 검증하는 테스트와는 구분합니다. 브라우저 테스트는 API/worker와 웹 서버를 시작하며 별도 e2e DB를 사용합니다. 이미 동작 중인 서버를 사용하면 해당 계정 데이터에 테스트 기록이 남으므로 전용 개발 환경에서 실행하세요.

검증 범위와 이 세션 실행 결과는 [docs/VERIFICATION.md](docs/VERIFICATION.md), 운영 절차는 [docs/BETA-RUNBOOK.md](docs/BETA-RUNBOOK.md)에 기록합니다.

## 배포

[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)의 Supabase migration → API/worker → Vercel 순서를 따릅니다. 외부 LLM 키는 필요하지 않습니다. 운영 모드는 개발 인증·SQLite를 거부합니다. GPS Storage bucket은 비공개, 크루 운영자도 개인 runs RLS를 우회할 수 없습니다.

## 문서

- [PRD](docs/PRD.md): 범위/사용 흐름/수용 기준
- [아키텍처·권한·계산 정책](docs/ARCHITECTURE.md)
- [API 명세](docs/API.md)
- [배포](docs/DEPLOYMENT.md)
- [14명 베타 운영](docs/BETA-RUNBOOK.md)
- [검증 결과](docs/VERIFICATION.md)

베타 이후 큰 규모에서는 GPX 작업 큐/내보내기를 별도 작업 서비스로 확장하고, edge rate limits·관측·백업 체계를 강화합니다. 의료 진단/부상 치료 서비스를 제공하지 않습니다.
