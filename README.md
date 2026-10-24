# oracle-seoul-retry

이 저장소는 두 가지 **서로 다른** 자동 확인을 한다. 둘 다 PC를 켜 둘 필요 없이 GitHub Actions가 대신 한다.

## A. 가입 화면에 한국이 홈 리전으로 뜨는지 확인 (`check_home_region.py`) — **가입 전, 지금 바로 켤 수 있음**
Oracle Cloud 가입 시 "홈 리전" 선택 목록에 **South Korea Central(서울)/North(춘천)이 2026-10-24 기준
한 달 넘게 아예 빠져 있는** 게 확인됐다 (신규 가입자에게 한국을 내어주지 않는 상태 — 웹 검색으로도 비슷한
보고가 여럿 있었음). 이 목록은 인증·캡차 없이 열리는 공개 API(`signup-api.cloud.oracle.com/20200828/region`,
Chrome 네트워크 탭으로 확인)라서, **Oracle 계정이 없어도** 그냥 주기적으로 호출해서 한국이 뜨는 순간을 잡을 수 있다.
- `check_home_region.py`가 10분마다(`.github/workflows/check-region.yml`) 이 API를 호출해 한국(서울/춘천) 포함 여부를 확인하고, 상태가 바뀔 때만(없다가 생기면/있다가 사라지면) 텔레그램으로 알린다.
- 필요한 Secrets은 `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` **뿐** — OCI 가입이나 API 키가 전혀 필요 없다.
- 뜨면 바로 `https://signup.cloud.oracle.com/`에서 가입을 진행하면 된다 (한 번 정하면 못 바꾸니, 뜬 걸 알림으로 확인하고 들어가서 신중하게 선택).

## B. 계정이 생긴 뒤: 무료 서버(Micro) 재고 확인 (`oracle_retry_once.py`) — **0단계(가입) 끝난 뒤에 쓰는 부분**
Oracle Cloud 서울(또는 춘천) 홈 리전에 Always Free E2.1.Micro 인스턴스 재고("Out of host capacity")가
풀리는지 GitHub Actions가 대신 계속 확인하고, 뜨자마자 생성한다.

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
