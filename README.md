# oracle-seoul-retry

Oracle Cloud 서울(또는 춘천) 홈 리전에 Always Free E2.1.Micro 인스턴스 재고("Out of host capacity")가
풀리는지 GitHub Actions가 대신 계속 확인하고, 뜨자마자 생성한다. **PC를 켜 둘 필요 없음.**

PC용 `..\oci_launch_retry.ps1`과 판단 로직은 같다 (중복/한도 확인 → 가용 도메인마다 생성 시도 →
재고부족/요청제한/한도초과/설정오류 분류). 다른 점은 반복을 PC의 72시간 루프 대신 **cron이 담당**한다는 것뿐이다.

## 0단계 (먼저 사용자가 직접) — `..\오라클_서울_서버확보_가이드.md` 1~5장
가입, PAYG 전환, 예산 알림, VCN(서브넷 OCID), `oci setup config`(API 키 등록)까지 끝낸다.
그 과정에서 이 값들이 나온다 — **채팅에는 붙이지 말고** 아래 "Secrets 등록" 명령에만 쓴다:
사용자 OCID, 테넌시 OCID, 지문(fingerprint), 리전, API 개인키 파일(`oci_api_key.pem`),
서브넷 OCID, SSH 공개키 내용.

## 저장소 만들기 (1회)
```powershell
cd C:\Users\motorhome\claude-test\오라클서울\gh-actions
gh repo create yestradamuss/oracle-seoul-retry --public --source=. --remote=origin --push
```

## Secrets 등록 (본인 터미널에서 직접 — 값은 저와의 대화에 붙이지 않기)
```powershell
gh secret set OCI_USER_OCID -R yestradamuss/oracle-seoul-retry
gh secret set OCI_TENANCY_OCID -R yestradamuss/oracle-seoul-retry
gh secret set OCI_FINGERPRINT -R yestradamuss/oracle-seoul-retry
gh secret set OCI_REGION -R yestradamuss/oracle-seoul-retry          # 예: ap-seoul-1
gh secret set OCI_COMPARTMENT_ID -R yestradamuss/oracle-seoul-retry   # 테넌시 OCID와 같은 값(루트 구획)
gh secret set OCI_SUBNET_ID -R yestradamuss/oracle-seoul-retry
gh secret set OCI_SSH_PUBLIC_KEY -R yestradamuss/oracle-seoul-retry   # tennis_oci.pub 파일 내용 전체
gh secret set OCI_PRIVATE_KEY -R yestradamuss/oracle-seoul-retry      # oci_api_key.pem 파일 내용 전체
gh secret set TELEGRAM_BOT_TOKEN -R yestradamuss/oracle-seoul-retry   # jbedu 봇과 같아도 되지만(명령 수신 안 함) 구분하려면 새 봇
gh secret set TELEGRAM_CHAT_ID -R yestradamuss/oracle-seoul-retry
```
`gh secret set <이름>`만 치면 다음 줄에 값을 붙여넣으라고 나온다 — 그 화면은 저장소 로그에 남지 않는다.
`OCI_IMAGE_ID`, `OCI_DISPLAY_NAME`은 선택이라 안 넣어도 된다(기본값 사용).

## 확인 순서
1. **`workflow_dispatch`로 1회 수동 실행**: GitHub 저장소 Actions 탭 → `oracle-seoul-retry` → `Run workflow`.
2. 로그에서 `[capacity]`(정상, 재고 부족)만 보이면 설정이 맞는 것이다. `[fatal]`이 보이면 Secrets 값을 다시 확인한다.
3. 수동 실행이 `[capacity]`로 끝나는 걸 확인한 뒤에만 `retry.yml`의 `schedule:` 주석을 풀어서 커밋·푸시한다.
4. 생성에 성공하면 텔레그램으로 공용 IP가 온다. 이후 실행은 "이미 있습니다"로 조용히 끝난다.

## 안전장치
- 치명적 오류(설정/인증/한도)는 스크립트가 종료코드 1로 끝나서 **GitHub가 실패 메일을 보낸다** — 재고 부족은 종료코드 0(정상)이라 메일이 안 온다.
- 비밀값은 GitHub Secrets에 암호화 저장되고 로그에 자동 마스킹된다. 저장소를 공개로 해도(Actions 무료 분수 제한 회피 목적) 비밀값 자체는 노출되지 않는다 — 공개되는 건 이 코드/워크플로 로직뿐이다.
