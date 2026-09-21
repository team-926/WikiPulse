# 이어서 하기 (2026-09-22 기준)

**다른 PC에서 다시 붙잡을 때 처음 읽는 문서다.** 순서·명령·막힐 지점만 적는다.
진행 상황은 Jira 가 정본이라 여기 적지 않는다.

~~[next-steps-2026-09-21](next-steps-2026-09-21.md)~~ → 이 문서가 대신한다 (2026-09-22).
그 문서는 "워커를 못 켠다"가 전제였다. **켰고, 돌았고, 화면까지 나왔다.**

한 줄 요약: **골든데이(2025-06-12)가 운영에서 끝까지 관통했다. 남은 건 2개월 구간과
일일 크레딧 상한이다.**

## 0. 상태 복구 (10분)

```
git checkout develop && git pull --ff-only
```

서버는 읽기만 하는 확인이다.

```bash
ssh app-server  -o BatchMode=yes "sudo docker ps --format '{{.Names}}|{{.Status}}'"
curl -s "https://wikipulse.example.com/api/v1/issues?size=1&source=replay" | head -c 200
```

⚠️ **화면 경로는 해시 라우팅이다.** `https://wikipulse.example.com/issues` 는 랜딩으로
떨어진다 — `https://wikipulse.example.com/#/issues` 를 쓴다. 2026-09-22 에 이걸로 한 번 헤맸다.

## 1. 어디까지 됐나 — 운영 화면 관통 (2026-09-22 실측)

`/#/issues` 에서 **데이터 출처 → 과거 재구성** 을 고르면 골든데이가 나온다.

| 확인한 것 | 값 |
| --- | --- |
| `Air India Flight 171` | 분석 완료 · 급증 10.1 · 편집 22회 · 조회수 25,426 |
| 연관 주식 | **BA (BOEING CO)** · YTRA (Yatra Online) |
| 한국어 요약 | 사고 경위·사망자 수까지 정확히 생성됨 |
| 상위 10건 | 전부 **분석 완료** — `top-per-snapshot=10` 과 일치 |

`수집 → 판정 → 클러스터 → 후보 → LLM 검증 → 종목 → 한국어 요약 → 화면` 이 전부 붙었다.

⚠️ **기본 화면은 LIVE 다.** 아무 설정 없이 `/#/issues` 를 열면 실시간 수집 이슈가 뜨고,
전부 "분석 준비"·종목 0 이다 — `SOURCE=replay` 라 LIVE 는 처리 대상이 아니다.
시연에서 출처 필터를 먼저 바꾸지 않으면 **빈 화면을 보여주게 된다.**

## 2. 현재 워커 설정 (EC2 `infra/service/.env`)

```
WIKIPULSE_MATCHING_SCHEDULER_ENABLED=true     SCHEDULER_SOURCE=replay     BATCHSIZE=20
WIKIPULSE_MATCHING_SUMMARY_ENABLED=true       SUMMARY_SOURCE=replay       BATCHSIZE=20
WIKIPULSE_MATCHING_VERIFICATION_ENABLED=true                              BATCHSIZE=20
TOPPERSNAPSHOT=10 (양쪽)
```

🔴 **`.env` 를 고칠 때는 `infra/edit-env.sh` 를 쓴다** (WP-178). `sed -i` 는 그룹
소유권을 날려 다음 배포를 죽인다 — 그걸로 네 번 터졌다.

되돌리기(워커 끄기):

```bash
ssh app-server -o BatchMode=yes "cd /home/ubuntu && infra/edit-env.sh /home/ubuntu/infra/service/.env WIKIPULSE_MATCHING_SCHEDULER_ENABLED=false WIKIPULSE_MATCHING_SUMMARY_ENABLED=false && cd infra/service && sudo BACKEND_IMAGE=\$(sudo docker inspect service-backend-1 --format '{{.Config.Image}}') docker compose up -d --force-recreate backend"
```

⚠️ `edit-env.sh` 는 저장소에 있지만 **서버에 자동으로 놓이지는 않는다.** 없으면 저장소에서
복사해 쓴다.

## 3. 크레딧

```
2026-09-21 기준선   used 15,446 / remain 84,554
골든데이 예상        약 12,000 (고유 issue_key 61건 × (검증 134 + 요약 64.7))
만료                2026-10-02 18:00 KST
```

`SOURCE=replay` 라 골든데이를 다 채우면 **소모가 자연히 0 이 된다** — LIVE 는 대상이 아니다.

🔴 **일일 총량 상한은 여전히 없다(WP-168 본체).** 지금은 출처를 좁혀 총량이 묶여
있을 뿐이다. `SOURCE` 를 비우거나 2개월 구간을 켜면 상한이 사라진다.

## 4. 오늘 들어간 것

| 이슈 | 내용 |
| --- | --- |
| `-168` | 워커 대상을 `source` 로 좁히는 노브. 🔴 두 값(scheduler·summary)은 같아야 한다 |
| `-177` | 스트리밍 회귀 테스트 데드라인 30초 → 180초. 이게 막혀 배포가 전부 멈춰 있었다 |
| `-178` | `infra/edit-env.sh` — `.env` 편집·권한 복구·러너 읽기 검증을 묶는다 |
| `-179` | 배포가 저장소 `compose.yaml` 을 서버로 민다 (diff 로그 + 백업) |

## 5. 다음 작업 후보

### 5-1. 🔴 `-168` 본체 — 일일 크레딧 총량 상한

지금은 "출처를 좁혀서" 총량이 묶인 것이지 상한이 있는 게 아니다. 2개월 구간을 켜는
순간 필요해진다.

### 5-2. 2개월 고정 구간 (2026-07-17~09-17)

운영에 **아직 0행**이다 — `-137`(sangeune) 진행 중. 들어오면:

```
하루 고유 61건 × 60일 = 3,660건 × 134 ≈ 490,000 크레딧
```

잔액으로 **17%(열흘치)** 밖에 못 덮는다. 상한을 1~2로 낮추거나 구간을 고르는 결정이 필요하다.

### 5-3. 화면에서 아직 비어 있는 것

골든데이 상세에서 실제로 "미제공"으로 뜨는 것들이다. 시연 전에 알아야 한다.

- **시계열 미제공** — 편집·조회수 추이와 기준선 자료가 없다
- **문서별 편집자 합계 미제공**
- **클러스터 멤버가 1개** — Clickstream 2025-06 덤프가 없어 버블맵 간선이 0이다
- **구조화된 상세 해석 미제공** — 요약 본문은 있지만 구조화 필드가 비어 있다

### 5-4. 간헐 실패 테스트 (WP-181)

`ExternalCallBeforeCharacterizationTest > e_연속폴_죽은_업스트림_재타격()` 이 develop
파이프라인 #214323 에서 한 번 떨어졌다가 재시도로 통과했다. 서킷브레이커 상태가 테스트
간에 공유돼 호출 수가 기대보다 적게 나오는 것으로 보인다(미확인).

⚠️ 이게 떨어지면 **deploy 스테이지가 통째로 건너뛰어진다.** 이번에도 그랬다 —
`-177` 과 같은 유형이다.

## 6. 함정 (2026-09-22 에 실제로 물린 것)

- 🔴 **EC2 `infra/` 는 저장소와 자동 동기화되지 않았다.** 서버 compose 가 31줄 / 저장소
  51줄이었고 `-165`·`-172`·`-176` 변수가 통째로 빠져 있었다. **기본값이 우연히 같아
  아무도 몰랐다.** `-179` 로 배포가 밀게 했지만, `infra/` 의 나머지 폴더(`db`·`nginx`·
  `hdfs`·`spark`·`pipeline`)는 여전히 수동이다
- 🔴 **`sed -i` 가 `.env` 그룹 소유권을 날린다.** 네 번째로 물렸다(#214248). `-178` 참고
- ⚠️ **pgserver 는 경로에 한글이 있으면 `initdb` 가 죽는다.** `FATAL: invalid byte
  sequence for encoding "UTF8": 0xb9` — 데이터 디렉터리뿐 아니라 **설치 경로**도 해당한다.
  Windows 사용자명이 한글이면 홈 밑이 전부 걸린다. `db/tests` 는 `WIKIPULSE_TEST_DSN` 으로
  실 PostgreSQL 을 가리켜 돌린다
- ⚠️ **한글 경로는 명령 치환을 거치면 깨진다.** `$(ls ...)` 로 받은 경로로 리다이렉트하면
  `No such file`, 셸이 직접 확장한 glob 은 멀쩡하다
- ⚠️ **화면은 해시 라우팅이다** (`/#/issues`). `/issues` 는 랜딩으로 떨어진다
