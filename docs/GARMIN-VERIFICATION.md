# 상세 기록·코칭 업그레이드 검증

2026-10-13. 기존 운영 main은 유지한 채 feature/garmin-coaching에서 구현하고 검증했습니다. 새 코드의 운영 배포는 Supabase 추가 migration 적용 이후 진행합니다.

| 검사 | 로컬 결과 |
|---|---|
| Python 전체 | 64개 통과: 기존 29개 회귀 포함 |
| 실제 PostgreSQL 정책/권한 실행 (PGlite) | 39개 assertion 통과 |
| 모바일·데스크톱 전체 브라우저 | 6개 통과 |
| 마지막 폼 정렬/접근성 수정 후 새 기능 흐름 재검사 | 2개 통과 |
| Next.js 빌드 / TypeScript | 통과 |
| FIT 단위 변환/CRC/실내 러닝/압축 제한 | 7개 통과 |
| 운영 새 버전 | 대기: Supabase 추가 migration 필요 |

원래 GPS 비공개 테스트의 문자열 'lat' 검사는 새 지표 이름 oscillation에도 반응했습니다. 테스트 개수를 유지하면서 중첩 JSON의 실제 좌표 키를 재귀적으로 검사하도록 강화했습니다. 다른 기존 테스트는 보존했습니다.

브라우저 검사는 실제 API와 worker를 실행하여 FIT 업로드/276W·166spm·0.96m 지표, 훈련 의도/RPE에 따른 피드백 변경, 수동 가민 정보, 비공개 경로, 실제 경기 기록 기반 목표 범위, 800m 인터벌 편집과 새로고침 후 영속성을 확인합니다. modal 키보드 닫기도 확인합니다. 샘플과 테스트 계정은 합성 자료이며 실제 훈련으로 자동 표시하지 않습니다.

발견한 테스트 환경의 빌드 폴더 충돌은 build와 browser를 순차 실행하여 해결했습니다. 새 select의 접근성 이름을 명시하고 모바일 버튼을 가리던 개발 배지를 비활성화했습니다. 원본/ZIP/삭제를 포함한 기존 브라우저 회귀도 통과했습니다.

## 이전 운영 버전에서 실제 확인한 범위

앱 https://running-coach-inky.vercel.app 및 API https://running-coach-ergr.onrender.com에서 운영 health/API proxy/PWA manifest 응답을 직접 확인했습니다. 사용자 로그인, 합성 GPX 업로드 분석 결과 2.224km·6분/km·140bpm 화면, 원본/ZIP/삭제 완료 보고, 주간 계획 및 크루 owner·active/초대 코드 화면도 확인했습니다. 새 FIT/코칭/편집 버전의 실제 Supabase Auth/Storage 검증을 대신하지 않습니다.

14명 다른 이메일 가입용 SMTP 설정, 여러 계정으로 하는 실제 Supabase 권한 smoke test, 무료 서버 절전 이후 재접속과 분석 재개는 아직 남아 있습니다. 이메일 설정은 앱 수정 요청으로 잠시 보류됐습니다.

## GitHub Actions 최종 결과

[Run 38368906738](https://github.com/yongseung716/Running-coach/actions/runs/38368906738)는 두 job 모두 성공했습니다. 검증한 코드 commit은 `d3c4d7cad5fe1901f1efc8637d0f32f487d5eb93`입니다. 업로드 표시/시간 결측 그래프 보완의 `timing_complete` 타입 누락을 원격 검사에서 발견해 수정한 뒤 전체 검사에 통과했습니다. 문서 후속 commit은 코드 변경 없이 이 결과를 기록합니다.

사용자가 추가 DB 설정의 `Success. No rows returned` 화면을 전달하고 요청한 migration의 실행 결과라고 명시적으로 확인했습니다. 검증된 기능 브랜치를 main에 병합하고 푸시했습니다.


## 운영 새 버전 확인 — 2026-10-13

배포 코드 `704ccae0b74ddedbd90afc694d5a03c26a43fb58`의 [main CI 38370443100](https://github.com/yongseung716/Running-coach/actions/runs/38370443100)는 기존 29개 회귀 및 전체 64개 Python 테스트, 39개 RLS 검증, 모바일/데스크톱 브라우저 6개 시나리오, 타입 검사, production 빌드와 프로세스 검사 모두 성공했습니다. Vercel의 해당 커밋 배포 상태도 success입니다.

공개 운영 smoke 검사 17개가 통과했습니다. 앱 200, 직접 API와 앱 proxy의 engine_version 1.1.0 및 production DB SELECT 1, 새 OpenAPI 경로와 프런트엔드 배포 코드, 로그인 전 개인 기록/프로필/훈련 catalog/코칭 접근 401, 잘못된 Origin 403, 허용 Origin의 빈 로그인 입력 422, PWA manifest/worker/icons 200을 확인했습니다. 계정을 생성하거나 메일을 보내지 않았습니다. 상세 응답은 `garmin-production-results.json`에 보존합니다.

사용자의 인증 세션/운영 비밀키를 보유하지 않으므로 새 버전의 실제 FIT 파일 Storage 업로드와 인증 후 신규 DB 컬럼 접근은 직접 확인하지 못했습니다. 사용자가 앱에서 강력 새로고침 후 프로필 기록 저장, Garmin 원본 FIT 업로드, 분석/코칭 확인 및 훈련 편집 저장을 진행하면 운영 사용자 흐름을 추가 검증할 수 있습니다. 로컬·CI 테스트는 재현 가능한 합성 FIT를 사용합니다.
