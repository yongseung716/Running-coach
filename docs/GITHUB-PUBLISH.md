# GitHub 게시 상태와 이력 보존

대상: `https://github.com/yongseung716/Running-coach.git`, 브랜치: `main`.

origin 설정과 main commit·push가 완료됐습니다. 소스·테스트·workflow가 원격 저장소에 보존되어 있고 GitHub Actions 두 job이 성공했습니다. 초기 HTTP 403은 저장소 소유 계정에 ChatGPT Codex Connector를 설치하고 대상 저장소 접근을 허용한 뒤 해결됐습니다. 검증 실행 링크는 [VERIFICATION.md](VERIFICATION.md)에 있습니다.

## 기존 workspace에서 게시

쓰기 연결이 확인되면 저장소 루트에서 실행합니다. force push를 사용하지 않습니다.

```bash
git status
git push -u origin main
gh run list --repo yongseung716/Running-coach --branch main
```

## 다른 PC에서 전체 commit 이력 복원

제공된 `running-coach-main.bundle`을 받은 뒤 같은 폴더에서 아래 명령을 실행합니다. bundle에는 commit 이력과 소스가 포함되고 .venv·실제 .env·runtime data·Git credential 설정은 포함되지 않습니다. PC에서 사용할 GitHub 계정의 Git 인증은 해당 PC에 정상 설정되어 있어야 합니다.

```bash
git clone -b main running-coach-main.bundle running-coach
cd running-coach
git remote set-url origin https://github.com/yongseung716/Running-coach.git
git push -u origin main
```

푸시 후 GitHub의 Actions 탭에서 `Running Coach checks`의 `Existing 29 regression tests`와 `verify` 결과를 확인합니다. 실패한 실행의 로그·실패 step을 기준으로 수정하며, 로컬 통과 결과를 원격 CI 통과로 취급하지 않습니다.
