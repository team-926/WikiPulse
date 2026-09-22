# 이어서 하기 (2026-09-22 기준)

**다른 PC에서 다시 붙잡을 때 처음 읽는 문서다.** 순서·명령·막힐 지점만 적는다.
진행 상황은 Jira 가 정본이라 여기 적지 않는다.

~~[next-steps-2026-09-21](next-steps-2026-09-21.md)~~ → 이 문서가 대신한다 (2026-09-22).
그 문서는 "워커를 못 켠다"가 전제였다. **켰고, 돌았고, 화면까지 나왔다.**

한 줄 요약: **골든데이는 관통했다. 오후에 LIVE 파이프라인이 세 겹으로 고장나 있던 걸
다 고쳤고, 지금은 위키미디어 상류가 멈춰서 기다리는 중이다.**

---

## 🔴 0. 지금 가장 중요한 사실 — 상류가 멈췄다 (WP-200)

**위키미디어 pageview 집계가 2026-09-21 12:00 UTC 부터 서 있다.** 우리 코드 문제가
아니고, 우리가 할 수 있는 게 없다.

| 소스 | 마지막 데이터 |
| --- | --- |
| `other/pageviews` 시간별 덤프 | 09-21 **11:00** 버킷 (파일 `-120000`, 21-Sep 14:18 게시) |
| **AQS 시간별 API** | 09-21 **11:00** 버킷 — **같은 지점** |
| `other/pageview_complete` 일별 | 09-**20** |
| **AQS 일별 per-article** | 09-**20** — **같은 지점** |
| `other/mediacounts` (같은 호스트, 다른 잡) | 09-21분 22-Sep 02:28 게시 — **정상** |
| EventStreams | 200 — **정상** |

🔴 **덤프 게시 문제가 아니라 집계 파이프라인 정지다.** 덤프와 API 는 배포 경로가 다른데
정확히 같은 지점에서 끊긴다. 같은 호스트의 `mediacounts` 는 정상 게시됐다.

⚠️ **AQS 폴백이 안 통한다.** "덤프가 안 오면 API 로 받자" 가 자연스러운 대안인데
**API 도 같은 지점에서 비어 있다.** 확인 안 하고 짜면 빈 응답만 받는다.

### 복구 판정 — 이 한 줄이면 된다

```bash
curl -s -o /dev/null -w "%{http_code}\n" -H "User-Agent: wikipulse/1.0 (<연락처>)" \
  "https://wikimedia.org/api/rest_v1/metrics/pageviews/top/en.wikipedia/all-access/2026/09/21"
```

`404` = 아직 정지. `200` = 복구. 덤프 말고 **API 를 보면** 게시 지연이 안 섞인다.

복구되면 **아무것도 안 해도 된다.** `live-cycle` 이 5분마다 파일을 찾고, 원장이 채워지며
대기 56,007건이 소화되기 시작한다.

### 선례 — 한 달 전에 똑같았다

[T435038](https://phabricator.wikimedia.org/T435038) (2026-08-15~19, **4일**). 증상이
글자 그대로 같다: 시간별 정지 + AQS 404 + 일별이 하루 먼저 끊김.

⚠️ **원인은 공개된 적이 없다.** 종료 코멘트가 "As far as I can tell, its all back now!"
가 전부다. 앞선 사례도 셋이다 (T427171 · T330184 · T370108). **반복되는 고장이고 근본
원인이 문서화된 적이 없다.**

⚠️ analytics SAL 에 정지 기간 내부 조치 흔적이 없었고, **신고 이틀 뒤에 복구됐다.**
신고가 트리거였을 가능성이 있다. 신고 초안은 이 문서 맨 아래 부록에 있다.

---

## 1. 상태 복구 (10분)

```
git checkout develop && git pull --ff-only
```

서버는 읽기만 하는 확인이다.

```bash
ssh app-server -o BatchMode=yes "sudo docker ps --format '{{.Names}}|{{.Status}}'"
curl -s "https://wikipulse.example.com/api/v1/issues?size=1&source=replay" | head -c 200
```

🔴 **비대화형 ssh 에서는 `sudo docker` 를 써야 한다.** 그냥 `docker` 는
`permission denied ... /var/run/docker.sock` 이 난다 (docker 그룹이 non-login 셸에
안 붙는다). 2026-09-22 에 이걸로 한 번 멈췄다.

🔴 **운영 DB 계정은 `usera609` 다** (`wikipulse` 아니다 — 그건 DB 이름).

```bash
ssh app-server -o BatchMode=yes "sudo docker exec postgres-postgres-1 \
  psql -U usera609 -d wikipulse -tAc \"SELECT max(version) FROM schema_migration\""
```

⚠️ **화면 경로는 해시 라우팅이다.** `https://wikipulse.example.com/issues` 는 랜딩으로
떨어진다 — `https://wikipulse.example.com/#/issues` 를 쓴다.

⚠️ ssh 별칭(`app-server`·`app-server`)은 **개인 설정**이다. 새 PC 에서는 팀 지침 문서 의
접속 문자열로 만들어야 한다.

---

## 2. 오후에 고친 것 — LIVE 가 세 겹으로 고장나 있었다

증상은 네 번 다 똑같았다: **`재판정 0`, 대기 증가.** 앞 단계를 고쳐야 다음 게 드러나서,
고칠 때마다 "풀렸다" 로 두 번 오판했다.

| # | 원인 | 이슈 |
| --- | --- | --- |
| 1 | 조회수 파일명 시각을 윈도우 **끝**이 아니라 시작으로 읽어 한 시간 밀림 | `-127` |
| 2 | 고친 코드가 **24시간 동안 서버에 안 닿음** (배포 경로 없음) | `-194`·`-196` |
| 3 | **조회수 0 문서를 미도착으로 오인**해 큐가 맨 앞에서 막힘 | `-199` |
| 4 | 상류 정지 (우리 밖) | `-200` |

### 2-1. `-199` — 덤프는 조회수 0 인 문서를 안 싣는다

그래서 `page_view_hourly` 에 행이 없는 것이 **"미도착"과 "0회" 둘 다**를 뜻했다.
`SELECT_DUE_SQL` 이 미도착으로만 읽어서 0회 문서가 영영 대기로 남고, 재판정이 오래된
순이라 **큐가 맨 앞에서 막혔다.** 실측: 0회 문서 **500건**이 뒤의 **53,982건**을 굶겼다.

적재 원장 **`page_view_hourly_ingest` (V14)** 를 새로 뒀다. 키 `(wiki, ts_hour)`.

```
원장에 있다 + page_view_hourly 행 없다  →  0회.   폐기까지 간다
원장에 없다                             →  미도착. 대기로 남는다
```

🔴 **`rows` 값이 아니라 행의 존재가 신호다.** LIVE 는 대기 목록의 문서만 선택적으로
받으므로(전수는 시간당 149만 행) 그 시간 후보가 전부 0회면 `rows=0` 이 된다.
`rows > 0` 을 도착 조건으로 쓰면 같은 버그를 반대편에서 다시 만든다.

### 2-2. `-202` — 만료가 상류 정지를 "문서 없음"으로 읽었다

만료는 `first_seen_at < now() - 36시간` 이었다. 그 전제("파일은 이미 나왔고 이 문서가
그 안에 없었다")는 **상류가 돌 때만 참이다.**

기준을 **상류 진행도**로 바꿨다 — 36시간 경과 **AND** 같은 wiki 의
`ts_hour >= window_start` 인 원장 행 존재.

| 상황 | 동작 |
| --- | --- |
| 상류 정지 | 원장이 안 늘어 **아무것도 안 버린다** |
| 그 시간만 결손 | 뒤 시간이 들어와 원장이 넘어가므로 36시간 뒤 정상 만료 |
| 상류 복귀 | **원장 행 하나만** 들어와도 오래된 후보 전부가 다시 만료 대상(`>=`) |

운영에서 읽기 전용으로 실증했다 (20시간 경계 가정):
**옛 규칙 2,506건 삭제 → 새 규칙 0건.**

⚠️ **원장이 비면 만료가 아무것도 안 버린다.** 첫 적재 한 번으로 해소되지만, 상류가
오래 멈추면 그동안 무한정 쌓인다. 상한은 별건으로 남겼다.

---

## 3. 서버에 올린 것 (2026-09-22 08:57 UTC)

| | 상태 |
| --- | --- |
| V14 마이그레이션 | 운영 적용 **08:56:36 UTC** (CI `deploy:backend`) |
| `data-pipeline` 3개 파일 | 수동 복사 — `candidate_store.py` · `recheck.py` · `pageview_hourly_ingest.py` |
| 백업 | `.bak-199-20260922-085706` (같은 디렉터리) |
| `live-cycle` · `edit-stream` | 재시작. 컨테이너 내부 md5 = 호스트 md5 확인 |
| 에러 | 없음 — `relation ... does not exist` 안 남 |

🔴 **`data-pipeline` 은 CI 로 안 올라간다.** 서버 bind mount
(`/home/ubuntu/wikipulse-local-test/data-pipeline`)에서 코드를 읽는다. 수동 절차:

```bash
# 1) 스테이징
ssh app-server -o BatchMode=yes 'mkdir -p /home/ubuntu/stage-199'
scp data-pipeline/spike/candidate_store.py data-pipeline/spike/recheck.py \
    data-pipeline/batch/pageview_hourly_ingest.py app-server:/home/ubuntu/stage-199/

# 2) 백업 후 교체 → 3) 재시작
#    (전체 스크립트는 이 세션 이력 참고. 요지는 cp -p 로 백업 → cp → docker restart)
ssh app-server -o BatchMode=yes 'sudo docker restart wikipulse-live-cycle wikipulse-live-edit-stream'
```

🔴 **순서가 있다. 마이그레이션 먼저, 파일 나중.** 반대로 하면
`relation "page_view_hourly_ingest" does not exist` 로 재판정·만료가 통째로 죽는다.

⚠️ **`live-cluster` 는 안 건드렸다.** 같은 마운트를 보므로 다음 재시작 때 새 코드를
쓴다. 지금 끊으면 도는 스냅샷이 깨진다.

---

## 4. 🔴 CI 가 배포를 조용히 취소한다 (WP-193, 두 번째 관측)

`interruptible: false` 가 두 deploy 잡에 **이미 붙어 있는데도** 배포가 취소됐다.
그 플래그는 **실행 중인 잡만** 지킨다 — 대기열에 있던 잡은 새 파이프라인이 밀어낸다.

```
17:38:26  MR !170 머지 (V14 포함)
17:42:34  다른 사람이 develop 에 머지
17:42:35  deploy:backend · check:migrations 가 started_at=null 인 채 canceled
```

🔴 **취소는 실패보다 위험하다.** 실패는 빨강이라 보이는데 **취소는 아무 데서도 안
보인다.** 머지한 사람은 "초록으로 머지됐다"만 본다. 미적용을 잡으라고 만든
`check:migrations` 조차 같은 이유로 같이 죽는다.

이번엔 뒤 파이프라인이 내 커밋을 포함해서 결과적으로 적용됐다 — **운이 좋았던 것이다.**

⚠️ **머지 후 운영 DB 로 직접 확인해야 한다.** 파이프라인 초록만 보면 안 된다:

```bash
ssh app-server -o BatchMode=yes "sudo docker exec postgres-postgres-1 \
  psql -U usera609 -d wikipulse -tAc \"SELECT max(version) FROM schema_migration\""
```

⚠️ 러너는 **`concurrent = 1`** 이다. 잡 10개가 순차로 돌아 develop 파이프라인 하나가
20~30분 걸린다.

---

## 5. 현재 워커 설정 (EC2 `infra/service/.env`)

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

⚠️ `edit-env.sh` 는 저장소에 있지만 **서버에 자동으로 놓이지는 않는다.**

---

## 6. 크레딧

```
2026-09-21 기준선   used 15,446 / remain 84,554
골든데이 예상        약 12,000 (고유 issue_key 61건 × (검증 134 + 요약 64.7))
만료                2026-10-02 18:00 KST
```

`SOURCE=replay` 라 골든데이를 다 채우면 소모가 자연히 0 이 된다.

~~🔴 일일 총량 상한이 없다~~ → **`-191` 로 들어갔다** (V13 `llm_daily_usage`, 원자적
소비 + `BudgetExceededException`). ⚠️ `-168` 본체(운영 값 결정·모니터링)는 남아 있다.

---

## 7. 다음 작업 후보

### 7-1. 상류 복귀 대기 — 지금은 이게 1번이다

복구 전까지 **LIVE 누적이 0** 이다. MVP 가 "고정 2개월 + 이후 LIVE 누적" 이라 며칠
날아가면 발표에서 보여줄 LIVE 구간이 그만큼 짧아진다.

- [ ] 하루 더 보고 안 풀리면 **Phabricator 신고** (부록 참고). 8월엔 신고 이틀 뒤 복구
- [ ] `-190` 재적재 — 중복 행 정책 필요
- [ ] 상류 정지를 **드러나게** 하기. 지금은 `live-cycle` 로그의 "대기 N" 이 정상 대기와
      상류 장애를 같은 모양으로 찍는다

### 7-2. 2개월 고정 구간 (2026-07-17~09-17)

운영에 **아직 0행**이다 — `-137`(sangeune) 진행 중. 들어오면:

```
하루 고유 61건 × 60일 = 3,660건 × 134 ≈ 490,000 크레딧
```

잔액으로 **17%(열흘치)** 밖에 못 덮는다. 상한을 1~2로 낮추거나 구간을 고르는 결정이 필요하다.

### 7-3. `-196` 남은 범위 — 배포 경로

`infra/live/compose.yaml` 로 **실물을 기술만** 했다. 실제 컨테이너는 여전히 수동
`docker run` 이다. 남은 것:

- [ ] 서버 컨테이너를 compose 로 인수인계 (LIVE 를 잠깐 끊어야 해서 별건)
- [ ] `data-pipeline` 변경을 서버로 옮기는 배포 경로
- [ ] **서버 코드가 develop 보다 낡았는지 드러내는 검사**

### 7-4. 화면에서 아직 비어 있는 것

골든데이 상세에서 실제로 "미제공"으로 뜨는 것들이다. 시연 전에 알아야 한다.

- **시계열 미제공** — 편집·조회수 추이와 기준선 자료가 없다
- **문서별 편집자 합계 미제공**
- **클러스터 멤버가 1개** — Clickstream 2025-06 덤프가 없어 버블맵 간선이 0이다
- **구조화된 상세 해석 미제공** — 요약 본문은 있지만 구조화 필드가 비어 있다

### 7-5. `-183` (클러스터 멤버 0)

**막혀 있다** — 상은이의 CORE 방향 결정과 CASCADE 결정이 먼저다. 2026-09-22 에 상은이는
`-183` 을 하고 있지 않다고 확인했다.

⚠️ 서버에 **`wikipulse-golden183-pg`** 컨테이너가 남아 있다 (07:46 UTC 생성, 볼륨
784 MB, `page_baseline` 806,759행). **누구 건지 확인 안 됐다.** 연결 0개·CPU 0.01% 라
해롭지 않아서 두었다. 정리 전에 주인을 찾을 것.

---

## 8. 함정 (2026-09-22 에 실제로 물린 것)

- 🔴 **비대화형 ssh 는 `sudo docker`** — 안 그러면 socket permission denied
- 🔴 **운영 DB 계정은 `usera609`** — `wikipulse` 는 DB 이름이다
- 🔴 **CI 가 배포를 조용히 취소한다** (§4). 파이프라인 초록 ≠ 배포됨
- 🔴 **`data-pipeline` 은 CI 배포 대상이 아니다.** 머지해도 LIVE 는 옛 코드로 돈다
- 🔴 **마이그레이션 먼저, 파일 나중**
- 🔴 **EC2 `infra/` 는 저장소와 자동 동기화되지 않는다.** 서버 compose 가 31줄 / 저장소
  51줄이었고 변수가 통째로 빠져 있었다 — **기본값이 우연히 같아 아무도 몰랐다**
- 🔴 **`sed -i` 가 `.env` 그룹 소유권을 날린다.** 네 번 물렸다. `infra/edit-env.sh` 를 쓴다
- ⚠️ **같은 증상이 서로 다른 원인에서 나온다.** `재판정 0` 이 네 가지 원인에서 똑같이
  나왔다. 하나 고치고 "풀렸다" 로 단정하면 안 된다 — 두 번 그랬다
- ⚠️ **"상류가 멈췄다" 도 확인 없이 단정하면 안 된다.** 처음엔 시간별만 보고 "시간별
  잡이 멈췄다" 로 볼 뻔했는데 일별까지 보니 계열 전체였다. 범위가 다르면 대응도 다르다
- ⚠️ **pgserver 는 경로에 한글이 있으면 `initdb` 가 죽는다.** `FATAL: invalid byte
  sequence for encoding "UTF8": 0xb9` — 데이터 디렉터리뿐 아니라 **설치 경로**도 해당한다.
  `db/tests` 는 `WIKIPULSE_TEST_DSN` 으로 실 PostgreSQL 을 가리켜 돌린다
- ⚠️ **한글 경로는 명령 치환을 거치면 깨진다.** `$(ls ...)` 로 받은 경로로 리다이렉트하면
  `No such file`, 셸이 직접 확장한 glob 은 멀쩡하다
- ⚠️ **화면은 해시 라우팅이다** (`/#/issues`)
- ⚠️ **bash heredoc 안의 `\n`·`\t`** 가 실제 줄바꿈으로 치환돼 파이썬 문자열 리터럴을
  깨뜨린다. 서버에 파일을 만들 때 두 번 물렸다 — `scp` 나 Edit 도구를 쓴다

---

## 부록. Phabricator 신고 초안

⚠️ **올리기 직전에 §0 의 복구 확인 한 줄을 먼저 돌려라.** `200` 이면 복구된 것이라
신고할 게 없다. 수치도 그때 다시 재서 갱신한다.

- 올릴 곳: https://phabricator.wikimedia.org/maniphest/task/edit/form/1/
- Project Tags: `Analytics-Data-Problem` (8월 선례 T435038 과 동일)
- Priority: Medium

### Title

```
Pageview data stalled since 2026-09-21 12:00 UTC: AQS and hourly dumps stop at the same point
```

### Description

```
Both the Analytics Query Service and the public pageview dumps stopped advancing
at the same point on 2026-09-21, and have not moved since. Other datasets on the
same dumps host are unaffected, which may help localize it.

All observations below were taken at 2026-09-22 09:00 UTC.

## Analytics Query Service

Hourly aggregate: the last hour served is 2026-09-21 11:00. Requesting anything
from 12:00 onward returns 404:

  curl -s -H "User-Agent: <ua>" \
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/aggregate/en.wikipedia/all-access/user/hourly/2026092112/2026092300"

  {"detail":"The date(s) you used are valid, but we either do not have data for
  those date(s), or the project you asked for is not loaded yet. ...","status":404}

Daily top: the last full day served is 2026-09-20.

  2026/09/19 -> 200
  2026/09/20 -> 200
  2026/09/21 -> 404

Daily per-article agrees (checked en.wikipedia/Iran, daily, user): last data
point is 2026-09-20.

## Dumps

other/pageviews (hourly) — last file is pageviews-20260921-120000.gz, published
21-Sep-2026 14:18. Every hour after that 404s.

  hourly file count per UTC day (from the directory index):
    20260917  24/24
    20260918  24/24
    20260919  24/24
    20260920  24/24
    20260921  13/24   (000000 .. 120000, then nothing)
    20260922   0/24

other/pageview_complete (daily rollup) — last is pageviews-20260920-user.bz2 /
pageviews-20260920-automated.bz2, published 21-Sep-2026 02:27 and 02:41. The
rollup for 2026-09-21 has not appeared; on the normal cadence it would have been
published around 2026-09-22 02:30.

## What still works

other/mediacounts on the same host published mediacounts.2026-09-21.v00.tsv.bz2
at 22-Sep-2026 02:28, on its usual schedule. So the dumps host and the general
publishing jobs appear healthy.

EventStreams (stream.wikimedia.org) is serving normally.

wikimediastatus.net reports no incidents for 2026-09-21 or 2026-09-22.

## Observation

The AQS API and the dumps are separate delivery paths but they stop at exactly
the same point in the data (hourly: 2026-09-21 11:00; daily: 2026-09-20). That
suggests the issue is upstream of both rather than in publishing.

## Prior occurrences

This has the same shape as:

- T435038 — Pageview data missing since 2026-08-14 (AQS 404 + hourly dumps
  stopped), resolved 2026-08-19
- T427171 — PageView tool not updated since 21 May 2026
- T330184 — Missing Pageviews Data (projectviews-20230220-230000)
- T370108 — Missed pageview data over API

## Impact

We run a pipeline that consumes the hourly files to decide whether a page's
views spiked. Candidates wait for their hour's file to arrive, so the backlog
just grows while this is stalled — currently ~56,000 pending windows covering
2026-09-21 12:00 onward. Nothing is lost as long as the files eventually appear.

Happy to run any additional checks that would help.
```

⚠️ 사내 이슈 키(`WP-*`)는 **넣지 않는다.** 외부 트래커에서 의미가 없다.
