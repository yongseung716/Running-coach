# 배포 지침

## 외부 계정이 필요한 작업

Supabase 프로젝트·DB 비밀번호·anon key·service_role key, 이메일 SMTP/확인 링크 설정, Vercel 프로젝트와 배포 권한, Docker를 지원하는 별도 Python API/worker 호스팅이 필요합니다. 이 저장소는 외부 프로젝트를 생성하거나 실제 배포하지 않습니다. 외부 LLM API는 핵심 기능에 필요하지 않으며 이 버전은 규칙 해설만 사용합니다.

## 1. Supabase

1. 운영/스테이징 프로젝트를 분리하고 region을 API와 가깝게 선택합니다.
2. Auth의 JWT Signing Keys에서 ES256 또는 RS256 비대칭 키를 사용합니다. legacy HS256 서명은 API에서 거부합니다. 이메일 확인을 켜고 Site URL/redirect allowlist를 최종 Vercel origin으로 설정합니다. SMTP를 설정하고 테스트 가입 이메일 도착을 확인합니다.
3. Supabase CLI로 링크 후 migration 적용: `supabase link --project-ref YOUR_REF`, `supabase db push`. 또는 SQL editor에서 `supabase/migrations/202610120001_initial.sql`을 검토 후 적용합니다. 기존 사용자가 있으면 profiles backfill을 별도로 수행합니다(신규 프로젝트 기준 migration).
4. `gpx-private` bucket의 public=false, 10 MiB limit를 확인합니다. storage.objects에는 client 정책을 만들지 않습니다. 원본 읽기/쓰기/삭제는 서버만 수행합니다.
5. Postgres connection string은 `postgresql+psycopg://...?...sslmode=require`. 비밀번호 특수문자는 URL encode. IPv4 전용 호스트면 session pooler(5432)를 사용합니다. transaction pooler는 SQLAlchemy prepared statement 설정 검토가 필요하므로 베타에서는 session/direct connection을 권장합니다.
6. API의 DB 접속 role은 authenticated로 `SET LOCAL ROLE` 가능한 backend 전용 role입니다. 보통 프로젝트 DB의 postgres 연결을 사용합니다. 클라이언트에 DB 비밀번호를 전달하지 않습니다. worker에는 별도 service DB 연결을 제공하며 API 사용자 세션은 authenticated로 강등합니다.

## 2. Python API와 worker

같은 Docker image를 API와 worker 두 서비스로 실행합니다. 저장소 루트 Dockerfile 경로는 `apps/api/Dockerfile`. API command 기본 uvicorn, worker command `python -m coach.worker`. 항상 켜진 worker가 필요하며 Vercel serverless에서 실행하지 않습니다.

```text
MODE=production
DATABASE_URL=postgresql+psycopg://USER:URL_ENCODED_PASSWORD@HOST:5432/postgres?sslmode=require
SUPABASE_URL=https://PROJECT.supabase.co
SUPABASE_ANON_KEY=<project anon key>
SUPABASE_SERVICE_ROLE_KEY=<server-only secret>
ALLOWED_ORIGINS=https://YOUR_FRONTEND_DOMAIN
STORAGE_BUCKET=gpx-private
```

호스팅 secret manager로 주입하고 로그·이미지·Git에 넣지 않습니다. URL의 password를 console에 출력하지 않습니다. `/health` DB 접근 확인, worker logs 및 stale queued/processing 수를 관측합니다. DB migration은 배포 전 실행하고 API는 자동 schema 변경하지 않습니다. Worker lease 120초보다 길게 걸리는 파일이 있으면 heartbeat/lease 조정을 먼저 적용합니다. worker는 큐를 선점할 수 있으므로 정상 shutdown 유예를 30초 이상 설정하세요.

애플리케이션 per-process rate limit에 더해 API ingress/edge에서 Auth 20회/분/IP, upload 제한, 최대 request body 10 MiB+multipart overhead를 설정합니다. API ingress는 가능하면 Vercel proxy만 허용하고 문서 endpoint는 운영 정책에 맞춰 제한합니다. 인증 쿠키를 쓰는 요청은 Origin allowlist가 필수입니다. 임의 preview Vercel origin을 wildcard로 허용하지 말고 스테이징에서 따로 설정하세요.

## 3. Vercel

Root Directory `apps/web`, 프레임워크 Next.js, repository root 설치/빌드는 `vercel.json` 명령 참조. workspace 외부 파일 포함 설정을 켭니다. 환경 변수 `API_INTERNAL_URL=https://YOUR_API_HOST` 설정 후 새 빌드. `NEXT_PUBLIC_*` Supabase service key는 사용하지 않습니다.

프론트 `/api/:path*`가 Python API로 rewrite되므로 쿠키는 프론트 origin에 저장됩니다. 운영 API는 Secure HttpOnly cookies를 사용합니다. 업로드 10 MiB가 Vercel rewrite/호스팅 제한에 걸리지 않는지 스테이징에서 확인하세요. 사용 플랜의 body 제한이 더 작다면 안내 limit를 낮추거나 별도 presigned 업로드 설계를 적용한 뒤 베타를 시작하세요.

실제 URL에서 manifest/icon/offline 설치 확인. iOS Safari와 Android Chrome에서 설치·로그인·로그아웃·재접속을 점검합니다. HTTPS 필수. service worker는 개인 API/운동 데이터/인증 HTML을 캐시하지 않습니다.

## 4. 필수 스테이징 smoke test

서로 다른 A/B/C 계정과 owner/admin/member 역할로 가입·이메일 확인, invite→pending→승인, 원본 업로드→completed, 세 명 동의→집계→한 명 철회 즉시 제한, 다른 사용자의 run UUID로 조회/다운로드/삭제 모두 404, 직접 Supabase REST로 역할·analysis 변경 차단, GPX 삭제/ZIP 내용/계정 삭제를 확인합니다. refreshed 세션이 재인증 제한을 우회하지 않는지도 확인합니다.

PGlite 테스트는 DB 정책을 검증하지만 Supabase 플랫폼 Auth/Storage·외부 hosting network까지 대신 검증하지 않습니다. 성공한 deployment URL, 커밋, migration, 실제 검증 시간을 운영 기록에 남긴 뒤 실제 베타 데이터를 수집합니다.
