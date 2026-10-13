# Render 무료 베타

초기 베타의 비용을 줄이려면 Free Web Service 하나에서 API와 분석 워커를 **각각 다른 프로세스**로 실행합니다. 기존의 API/워커 분리 배포도 지원합니다. 무료 제공 범위는 사업자의 제한에 따르며 상시 실행을 보장하지 않습니다.

## 무료 서비스의 제한

2026-10-13에 확인한 [Render 공식 문서](https://render.com/docs/free) 기준입니다.

- 15분 동안 들어오는 요청이 없으면 서버가 절전되며 워커도 멈춥니다.
- 다음 요청으로 서버를 다시 시작하는 데 약 1분이 걸릴 수 있습니다. 로그인이나 업로드가 시간 초과되면 기동 완료 후 다시 시도하세요.
- 중단된 분석은 다음 시작 시 Supabase DB의 대기 작업 또는 만료된 작업 임대에서 재개합니다. 앱의 완료 상태로 실제 분석 완료를 확인하세요.
- 로컬 파일은 절전/재배포 시 사라집니다. 운영 모드는 Supabase PostgreSQL과 비공개 Storage를 사용하며 SQLite나 로컬 GPX 보관을 사용하지 않습니다.
- 워크스페이스 전체 무료 실행 시간은 월 750시간입니다. 다른 무료 서비스와 공유합니다. 대역폭과 빌드 한도도 적용됩니다.
- 인위적인 keep-alive로 절전을 회피하지 않습니다. 지속적인 처리나 안정적인 응답 시간이 필요해지면 유료 API/별도 워커로 전환하세요.

## Render 화면 설정

`New Web Service`에서 GitHub `yongseung716/Running-coach`를 연결합니다.

| 항목 | 값 |
|---|---|
| Name | `running-coach-api` (중복 시 다른 이름) |
| Branch | `main` |
| Runtime / Language | `Docker` |
| Region | Supabase와 가까운 지역 (예: Singapore) |
| Root Directory | 비워 두기: 저장소 루트 |
| Dockerfile Path | `apps/api/Dockerfile` |
| Docker Build Context Directory | `.` |
| Docker Command (Advanced) | `python -m coach.serve` |
| Instance Type | **Free — $0/month** |
| Health Check Path | `/health` |

Docker Command가 기본 uvicorn이면 워커가 실행되지 않습니다. 반드시 위 명령으로 바꾸세요. 런처는 Render의 `PORT` 환경 변수에 맞춰 API를 실행합니다. API 또는 워커가 죽으면 나머지 프로세스도 종료하고 실패를 반환합니다. Supabase migration을 이미 적용했다면 다시 실행하지 않습니다.

## 필수 환경 변수

Render의 **Environment Variables / Secrets 입력란에만** 저장합니다. 비밀키/DB 비밀번호를 채팅, GitHub 소스, 스크린샷에 넣지 않습니다.

```text
MODE=production
DATABASE_URL=postgresql+psycopg://USER:URL_ENCODED_PASSWORD@SESSION_POOLER_HOST:5432/postgres?sslmode=require
SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co
SUPABASE_ANON_KEY=<Supabase project anon key>
SUPABASE_SERVICE_ROLE_KEY=<Supabase project service_role key, server only>
ALLOWED_ORIGINS=https://YOUR_FINAL_VERCEL_HOST
STORAGE_BUCKET=gpx-private
```

IPv4 연결에는 Supabase의 session pooler를 사용합니다. DB 연결 수는 API와 워커 모두를 고려합니다. `ALLOWED_ORIGINS`는 최종 프런트 URL을 확정한 후 업데이트합니다. wildcard나 개발 HTTP origin을 허용하지 않습니다. API key는 JWT 서명 키와 다릅니다. 기존 어댑터에 맞춰 anon/service_role API key를 사용하고 JWT 서명은 ES256/RS256으로 유지합니다.

Free 표시와 필수 설정을 확인한 후 Deploy를 누릅니다. 별도의 유료 Background Worker, Render Postgres, 영구 디스크를 만들 필요가 없습니다. DB와 GPX는 Supabase를 사용합니다. 유료 워크스페이스 업그레이드도 필요 없습니다.

## 실제 서비스 검증

Vercel의 `API_INTERNAL_URL`에 실제 Render HTTPS URL을 설정합니다. Supabase와 Vercel의 무료 범위와 이용 조건도 각각 확인합니다. Supabase Auth의 Site URL, redirect allowlist, 이메일 확인/SMTP도 최종 URL에 맞춥니다. 공개 전 [DEPLOYMENT.md](DEPLOYMENT.md)의 실제 서비스 smoke test를 수행합니다.

추가로 15분 이상 접속하지 않은 뒤 재접속, 로그인, GPX 처리 재개를 확인합니다. 참가자에게 무료 서버의 지연 가능성을 알리고 분석 완료를 확인한 결과만 사용합니다. 로컬/CI 검증은 Render와 Supabase 실서비스 연결 성공을 의미하지 않습니다.
