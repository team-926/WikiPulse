# 이어서 하기 (2026-09-23 기준)

**다른 PC에서 다시 붙잡을 때 처음 읽는 문서다.** 순서·명령·막힐 지점만 적는다.
진행 상황은 Jira 가 정본이라 여기 적지 않는다.

~~[next-steps-2026-09-22](next-steps-2026-09-22.md)~~ → 이 문서가 대신한다.
**그 문서의 §0-A·§0-B·§8(함정)은 아직 유효하니 한 번 읽어 둔다** — 여기서는 그 뒤에
일어난 것만 적는다.

한 줄 요약: ~~기준선 적재 경로를 만들어 운영에 켰다. 남은 건 기준선 잡을 주기적으로
돌리는 것이다.~~ → ~~(오전) 그 이틀의 replay 를 운영에 올리는 게 남았다~~ → **(오후 갱신)
시연 이틀(07-17·08-02)의 replay 가 운영에 올라갔고, 시연 스냅샷 3개만 매칭·요약 워커가
채우는 중이다. GDELT 합집합이 운영에서 처음 살아났다. 검증 나머지는 09-24 09:00 KST 예산
리셋 뒤에 돈다 (§A-7).**

---

## A. 2026-09-23 오전에 바뀐 것 — 먼저 읽는다

### A-1. 🔴 시연일 확정: **2026-07-17 · 2026-08-02** (UTC 날짜)

| 날 | 이슈 (replay 루트) | 종목 | LLM 검증 (운영 프롬프트, 3회) |
| --- | --- | --- | --- |
| 07-17 | `The Odyssey (2026 film)` 매시 1위 · 22시 `IMAX` 루트 | IMAX (CMCSA) | IMAX→IMAX mini 3/3 · 영화→IMAX mini 3/3 (nano 2/4) |
| 08-02 | `SummerSlam (2026)` (WWE) | **TKO** (WWE 모회사) | mini 3/3 · nano 2/3 |

~~§2-4 의 07-25 NSC↔UNP~~ → **탈락.** spike 는 정상인데 그 시점 views **78위/165** 라 ROOT
SELECTION(시점당 상위 20, 컷 1,176회)에서 빠진다 — 현행 규칙의 정상 동작이다(-214, 인계 덤프로
확인). 규칙을 결과에 맞춰 바꾸지 않는다.

⚠️ **구조적 발견**: 루트를 절대 조회수 상위 20 으로 뽑으면 연예·스포츠가 자리를 다 차지한다.
2개월 루트 22,080 중 상장사 문서는 41번이고 그중 27번이 Google(크롤러)이다. 기업 뉴스는 원리상
잘 안 들어온다 — 규칙 변경은 제품 논의거리다(-161 영역), 시연용으로 건드리지 않는다.

### A-2. 운영 설정 (서비스 EC2 `.env`) — 🔴 오후에 다시 바뀌었다

~~백엔드 `82bfe1af`, SNAPSHOT_DAYS=2026-07-17,2026-08-02~~ → **백엔드 `e9845b44` (2026-09-23 15:40 KST)**:

```
WIKIPULSE_MATCHING_SCHEDULER_SOURCE=replay                    # 원래 있던 값
WIKIPULSE_MATCHING_SUMMARY_SOURCE=replay
WIKIPULSE_MATCHING_SCHEDULER_SNAPSHOT_DAYS=2026-07-17T01:00,2026-07-17T22:00,2026-08-02T19:00
WIKIPULSE_MATCHING_SUMMARY_SNAPSHOT_DAYS=(같은 값)            # -215 시각 한정. 검증도 이걸 따른다
WIKIPULSE_MATCHING_SCHEDULER_TOPPERSNAPSHOT=5                 # 10 → 5
WIKIPULSE_MATCHING_SUMMARY_TOPPERSNAPSHOT=5
WIKIPULSE_MATCHING_GMS_VERIFICATIONMODEL=gpt-5.4-mini         # nano 에서 올림
WIKIPULSE_MATCHING_BUDGET_VERIFICATIONCALLS=400               # 🔴 임시. 300 으로 되돌린다(A-7)
WIKIPULSE_MATCHING_SUMMARY_ENABLED=true                       # 요약 모델은 Sonnet 유지
# WIKIPULSE_MATCHING_VERIFICATION_TIER3THRESHOLD 는 안 넣었다 — 새 기본값 0(게이트 끔, -222)
```

`.env` 백업: `.env.bak-215*` · `.env.bak-mini-*` · `.env.bak-budget-*` · `.env.bak-summary-*`

- mini: 시연 쌍 포함 양성 8쌍 **24/24**, 오탐 8/24 (nano 19/24 · 오탐 7/24, GDELT 컨텍스트 없이).
  호출당 약 32 크레딧 (nano 8.8). 검증 일일 상한 300 이면 하루 최대 약 9,600
- 🔴 **두 날을 다 채우면 워커를 끄거나 상한을 내린다.** 잔액 약 62,900 (09-23 12시), 만료 10-02
- ⚠️ 모델은 `.env` 에만 있다. 저장소 기본값(compose·`application.yml`)은 여전히 nano

### A-3. ~~남은 순서~~ → 오후에 전부 끝냈다 (기록으로 남김)

✅ 1 · 2 · 3 완료 — 5436 덤프 수령(sha256 `04f33ffd…`), 운영 적재(이슈 811 · 멤버 940 ·
spike 3,583, 백업 `~/backups/wikipulse-pre157-20260923-043147.dump`), !189 배포. 4 는 A-7.

1. **5436 preview 덤프 받기** (sangeune에게 요청함). 5435(인계 메인)의 클러스터는 **옛 규칙**
   결과다. 운영 규칙(ROOT+CORE, -161) 결과는 5436 에만 있다. spike 는 둘이 같다
2. **이틀만 운영에 적재** — `tools/replay_demo_load.py` (-157)
   ```bash
   python tools/replay_demo_load.py --src "$SRC_5436" --dst "$PROD_DSN" \
     --days 2026-07-17,2026-08-02 --dry-run      # 먼저 센다
   ```
   `wiki_page.id` 를 `(wiki, title)` 로 재매핑한다. 5435 → 빈 DB 리허설에서 이슈 940 ·
   멤버 2,934 · 간선 1,994 · spike 4,088, 원본과 자연키 다이제스트 일치. 재실행은 멈추고
   `--replace` 로만 교체된다(🔴 그날 요약·종목도 CASCADE 로 지워진다). 운영 적재 전에 백업
3. **!189 머지** (-213, LLM 입력 = 도입부 전체). 07-17 영화 문서의 IMAX 문장이 10번째라
   이게 없으면 영화 이슈에서 IMAX 가 잘린다. 머지 전 팀에 알린다(A-4)
4. 워커가 두 날을 채우면 화면 확인 → 워커 끄기

### A-4. ⚠️ 오늘 물린 함정 두 개

- 🔴 **연속 머지로 백엔드 배포가 통째로 빠졌다.** 10:42~11:01 develop 머지 4건 중 앞 3개
  파이프라인이 취소됐고, 마지막(data-pipeline 만 변경)은 `changes` 가 직전 커밋만 봐서
  `deploy:backend` 를 **만들지 않았다.** 파이프라인은 초록이었다. 운영은 10:15 버전에
  머물렀다. → develop 에서 **수동 파이프라인**(Run pipeline)을 돌리면 `changes` 가 참이라
  배포가 붙는다. `check:migrations`(-193) 는 **코드 배포 누락은 못 잡는다**
- 🔴 **`.env` 끝 줄바꿈이 없으면 `edit-env.sh` 가 새 키를 마지막 줄에 이어 붙인다.**
  `WIKIPULSE_PAGETITLE_ENABLED=trueWIKIPULSE_...` 가 됐다(재생성 전에 발견·복구). 수정 MR
  !193(-218). 머지 전이면 서버의 `/tmp/edit-env-218.sh`(수정판)를 쓴다

### A-5. 기준선 (-212)

`live-cycle` 이 하루 한 번 `page_baseline` 을 굴린다(!187, 서버 반영 완료). 창 끝은
`(now − 38h)` 의 전날 — 대기 중인 급등이 자기 기준선에 섞이지 않게. 첫 적재는
**2026-09-23 14:00 UTC(23:00 KST)**, 전부 표본 7일 미만. 7일 이상 슬롯은 09-29 전후.
§2-1 은 끝났고 §2-2 는 그대로다.

### A-6. 🔴 오후에 알아낸 것 — GDELT 합집합이 운영에서 0 이었다

명세 §6.3 은 후보 = (a) 임베딩 ∪ **(b) GDELT(주력)** 인데, 운영 `cluster_org_mention` 은 **0행**,
후보 4,740건이 **100% `EMBEDDING_ONLY`** 였다. HDFS `/wikipulse/raw/gdelt` 는 빈 폴더, 수집기
컨테이너도 드라이버 배선도 없었다(-148 로컬 Milton 관통이 유일한 실행). 게다가 `gkg/predicate.py`
가 **테마 ∧ 지역** 술어만 만들어 영화·스포츠·기업 이슈에서는 수집해도 전부 실패했다.

한 일 (시연 이틀만):
- GKG 백필 — 서비스 EC2 `~/wikipulse-local-test/data-pipeline/data/gdelt-data` (07-16~17 ·
  08-01~02, 384 파일 1.5 GB, 결손 0). 하루는 스냅샷 직전 24시간 창 때문에 앞날까지 받았다
- **키워드 술어**(-221, !197 머지 전) — 테마·지역이 둘 다 실패하면 씨드 제목을 기사
  제목(Extras `PAGE_TITLE`)·기관명에서 찾는다. 별칭 3개(universal pictures·studios→CMCSA,
  espn→DIS). 운영에는 서버 코드 사본을 건드리지 않고 일회성 컨테이너에 `gkg/` 만 덮어 돌렸다
- 결과 `cluster_org_mention`: Odyssey 29 (CMCSA 140) · IMAX 3 (IMAX 2,389 · CMCSA 127) ·
  SummerSlam 18 (DIS 35 · NFLX 11.5). 후보가 **BOTH·GDELT_ONLY** 로 처음 생겼다

⚠️ 처음 드라이버를 돌리기 전에 한 슬롯으로 술어부터 확인했어야 했다 — 전체 백필 뒤에야
술어 실패를 알았다.

- 🔴 **3등급 게이트(N=2)를 영구히 껐다** (-222, !200 배포). SummerSlam 에서 GDELT 의 DIS·NFLX 가
  먼저 통과하자 임베딩 정답 TKO 가 영구 스킵됐다. 이제 이슈당 후보 전부(최대 30) 검증 —
  **범위를 풀면 일일 상한에 금방 닿는다.** 되살리려면 `…VERIFICATION_TIER3THRESHOLD=2`
- 🔴 **검증 워커에 범위 한정이 전혀 없었다** (-215 !198). 날짜 필터 전 오늘 00~02:28 UTC 에
  골든데이 후보로 검증 300회가 다 나갔다. 이제 scheduler 의 source·snapshot-days 를 따른다
- LLM 검증 실측(mini, GDELT 컨텍스트 포함, 3회): Odyssey→CMCSA 3/3 · IMAX→IMAX 3/3 ·
  SummerSlam→TKO 3/3 · →DIS 2/3 · IMAX→CMCSA 2/3("있을 수 있다" 추측) · SummerSlam→NFLX 3/3
  (**일반론 통과 — 오탐으로 본다**). 기관명이 컨텍스트에 있으면 프롬프트가 느슨해진다 → lavendmin 공유
- 요약 모델 mini 전환은 **보류** — 한국어 요약은 mini 로 잰 적이 없다. 시연 이슈 3개를
  Sonnet·mini 로 나란히 비교한 뒤 정한다

### A-7. 🔴 09-24 09:00 KST(UTC 자정) 뒤 할 일

1. 검증 리셋 뒤 남은 약 210회가 돈다 — id 내림차순이라 08-02 → 07-17 22시 → 07-17 01시(Odyssey)
   순. 확인:
   ```sql
   SELECT ic.snapshot_ts, p.title, count(*) FILTER (WHERE cs.check_state='DONE') done,
          string_agg(cs.ticker, ',') FILTER (WHERE cs.verified) tickers
     FROM cluster_stock cs JOIN issue_cluster ic ON ic.id=cs.cluster_id
     JOIN cluster_member cm ON cm.cluster_id=ic.id JOIN wiki_page p ON p.id=cm.page_id
    WHERE ic.snapshot_ts IN ('2026-07-17 01:00+00','2026-07-17 22:00+00','2026-08-02 19:00+00')
    GROUP BY 1,2 ORDER BY 1,2;
   ```
   기대: SummerSlam 에 **TKO** · IMAX 에 **IMAX** · Odyssey 에 **CMCSA**
2. 화면 확인 — `https://wikipulse.example.com/#/issues` 에서 시점을 그 세 스냅샷으로
3. **채워지면 되돌린다**: `BUDGET_VERIFICATIONCALLS=300`, 검증·후보·요약 워커 `ENABLED=false`
   (`/tmp/edit-env-218.sh` 또는 !193 머지 뒤 `infra/edit-env.sh`) → 백엔드 재생성
4. 정리: 운영 postgres 임시 DB `replay_src_5436` DROP · 서비스 EC2 `/tmp/{gkg221*,edit-env-21*.sh,
   vec_*,p5436*}` · GDELT 원본 1.5 GB(다시 쓸 계획 없으면)
5. 머지 대기 MR: !193(-218 edit-env) · !196(-157 적재 도구·이 문서) · !197(-221 GDELT 키워드)

---

## 0. 지금 운영 상태 (2026-09-22 23:20 UTC 실측)

```
schema_migration         14, 15, 16          ← V15 계정·북마크 · V16 모바일 몫
page_view_hourly         173,733행 (모바일>0 25,363) · 최신 2026-09-22 18:00Z
spike_candidate          11,858 대기
page_baseline            0행                 ← 🔴 아직 비어 있다. 잡을 안 걸었다
issue_cluster            replay 413 · live 627
컨테이너                 live-cycle · live-cluster · edit-stream · spark-worker 전부 Up
```

`live-cycle` 이 **`PAGEVIEW_MIN_VIEWS=50`** 으로 돌고 있다 (2026-09-22 22:50 UTC 재생성).

### 🔴 이게 어젯밤에 바뀐 핵심이다

운영 `page_baseline` 이 0행이라 명세 §3.2 3번의 `z >= 3 AND 2배 이상` 이 **한 번도 발동한
적이 없었다.** 늘 절대 하한(100회)만으로 판정했다. 원인은 조회수를 **후보 문서만** 적재해서
`(문서, 시간대)` 별 28일 이력이 안 쌓인 것이다 — `sample_days` 가 1 근처에서 멈춘다.

→ `WP-212`. 하한 적재(`--min-views`)와 기준선 드라이버
(`spike/baseline_from_views.py`)를 넣고 **적재 쪽만 운영에 켰다.**

### 켠 것이 실제로 도는 것을 확인했다 (윈도우 2026-09-22 18:00Z 재적재)

| | 전 | 후 |
| --- | --- | --- |
| 그 시간 행 | 2,996 (후보만) | **28,081** |
| `mobile_views > 0` | 0 | **25,363** |
| 평균 모바일 비중 | — | **0.602** |
| 최소 조회수 | — | **1** ← 후보는 하한과 무관하게 남는다(`candidates` 계약) |

---

## 1. 상태 복구 (5분)

```
git checkout develop && git pull --ff-only
```

⚠️ **ssh 별칭(`app-server`)은 개인 설정이다.** 새 PC 에서는 팀 지침 문서 의 접속 문자열로
만든다. 이 PC(집)에서는 아래 두 개가 더 걸렸다 — 교육장 PC 는 사용자명이 달라 안 걸릴 수도 있다.

- 🔴 **Git Bash(Bash 도구)의 `ssh` 가 한글 홈 경로에서 깨진다.** `Could not resolve
  hostname` 이 나는데 원인은 DNS 가 아니라 `/c/Users/<user>...` 로 홈을 못 찾는 것이다.
  **PowerShell 도구에서 Windows `ssh.exe`** 를 쓴다.
- ⚠️ PowerShell 5.1 은 native exe 에 큰따옴표를 안 넘긴다. **작은따옴표 문자열 안에 `\"`**
  를 쓴다. `$` 는 PID 등으로 치환되니 SQL 에 `$$` 를 쓰지 말고 `chr()` 로 우회한다.

읽기만 하는 확인:

```bash
ssh app-server -o BatchMode=yes "sudo docker ps --format '{{.Names}}|{{.Status}}'"
curl -s "https://wikipulse.example.com/api/v1/issues?size=1&source=replay" | head -c 200
```

🔴 비대화형 ssh 는 **`sudo docker`** · 운영 DB 계정은 **`usera609`** · 화면은 **`/#/issues`**
(해시 라우팅).

---

## 2. 남은 일 — 이 순서로

### 2-1. ~~🔴 기준선 잡을 주기적으로 돌린다 (`-212` 마지막 조각)~~ → 완료 (!187, §A-5)

드라이버는 서버에 올라가 있는데 **부르는 자리가 없다.** 지금은 손으로만 돈다:

```bash
ssh app-server -o BatchMode=yes 'sudo docker exec wikipulse-live-cycle \
  python3 -m spike.baseline_from_views --dry-run'
```

⚠️ **지금 돌리면 전부 얇게 나온다** — 이력이 며칠치뿐이라 `sample_days < 7` 이고
`detector` 는 기존 fallback 을 그대로 쓴다. **깨지는 게 아니라 아직 안 좋아진 상태**다.
경로가 도는지 확인하는 용도로만 본다.

할 일: 하루 한 번 도는 자리를 만든다. 후보 둘 —
- `live-cycle` 주기 안에서 하루 한 번 (코드 변경. 락이 이미 있어 중복 실행은 안 된다)
- 별도 컨테이너/cron (⚠️ `infra/live/compose.yaml` 이 실물을 기술만 하고 실제는 수동
  `docker run` 이다 — `-196` 과 묶인다)

### 2-2. 며칠 뒤 확인 → `-212` 인수조건 마감

```bash
ssh app-server -o BatchMode=yes 'sudo docker exec postgres-postgres-1 psql -U usera609 \
  -d wikipulse -tAc "SELECT count(*) slots, count(*) FILTER (WHERE d >= 7) thick, \
  round(avg(d),2) avg_days FROM (SELECT page_id, EXTRACT(HOUR FROM ts_hour)::int hod, \
  count(DISTINCT ts_hour::date) d FROM page_view_hourly GROUP BY 1,2) s"'
```

2026-09-22 기준 **슬롯 122,829 · 평균 1.00일 · 7일 이상 0개**였다. 이 수치가 올라가야 한다.
그 다음 `spike.view_baseline` 이 NULL 이 아닌 행과 `view_ratio` 가 나오는지 본다.

**검증 사례**(어젯밤 실측): `Neatsville, Kentucky` 1.2배 · `Limonene` 1.1배 는 **폐기돼야**
하고, `Lizzie Borden` 49.8배 급은 확정돼야 한다.

### 2-3. 골든데이 `issue_report` 0행 복구

🔴 **시연 경로가 지금 깨져 있다.** 2026-09-22 08:50 UTC 에 누가 replay 클러스터링을 다시
돌려 `issue_report` 가 CASCADE 로 전부 날아갔다. 413건이 전부 `DETECTED` 다.

⚠️ **상은이에게 "replay 클러스터 또 돌릴 거냐" 를 먼저 확인한다.** 먼저 채우면 다음
재클러스터링에서 또 날아가고 크레딧만 두 번 나간다 (만료 2026-10-02).

복구 비용은 요약 61회 ≈ 2.5k~3.8k 크레딧 (잔액 67,817 의 5% 내외).

### 2-4. ~~시연일 결정 — 2026-07-25 (NSC ↔ UNP 합병 제안)~~ → **07-17 · 08-02 로 대체 (§A-1)**

2개월 구간에서 찾았다. 지금 관문으로 **실제로 잡히는** 날 중 유일하게 다섯 조건을 다
만족한다:

| 날 | 동반 급등 | 티커 |
| --- | --- | --- |
| **07-25 NSC↔UNP** | NSC **6.0배** · UNP **2.4배** (CSX 1.0배로 안 움직임) | **NSC·UNP 둘 다 마스터에 있고 임베딩도 있다** |
| 08-20 Charter↔Cox | Charter 5.0 · Cox 7.1 · Spectrum 4.9 | CHTR 만 (Cox 비상장) |
| 09-15 Kraft Heinz | KHC 4.5 · Kraft Foods 11.9 | KHC |

편집 요약이 `/* Proposed merger */` 로 사건을 지목하고, 조회수 6.0배로 두 관문을 통과한다.
🔴 **다만 2개월 구간이 운영에 아직 0행이다**(`-137`, 상은이). 들어와야 화면에 뜬다.

### 2-5. 그 외

- `-190` 재적재 (중복 행 정책 필요)
- `-183` 간선 0 — CORE 경로에 `cluster_edge` 배선이 없다. 골든데이도 0행. 상은이 결정 대기
- `spike/tests/test_signal_lag.py::test_표준편차가_0이면_z를_안_쓴다` 가 **전부터 깨져 있다**
  (내 변경 전에도 실패). 상수 시계열에서 `z=3.4e+17` 이 나온다 — 0 나눗셈 방어 누락으로
  보인다. 별건

---

## 3. ⚠️ 어젯밤에 물린 함정 (전부 실제로 당한 것)

- 🔴 **MR 을 연달아 머지하면 앞 파이프라인이 취소된다.** 러너가 `concurrent = 1` 이라
  `interruptible: false` 로도 대기열 잡은 안 지켜진다. 내가 `!181`·`!182` 를 2분 안에
  머지해서 **남의 배포(MR !180, 계정·북마크 + V15)까지 밀어냈다.**
  → **머지는 하나씩, 앞 파이프라인이 끝난 뒤에.** `.gitlab-ci.yml` 313~317행에 같은
  시나리오가 이미 적혀 있었다(`-193`).
- ✅ **`check:migrations` 가 그걸 잡았다.** "남은 마이그레이션: V15__page_view_hourly_
  mobile.sql, V15__accounts_and_bookmarks.sql" 로 **미적용과 번호 중복을 한 번에** 드러냈다.
  그 잡이 없었으면 운영에서 적용 순서가 갈렸을 것이다.
- 🔴 **마이그레이션 번호가 겹쳤다.** 같은 스프린트에서 `-203` 이 V15 를 먼저 썼다.
  `-117`(V5) 과 같은 상황이고, 관례대로 참조가 적은 쪽(내 것)을 **V16** 으로 옮겼다.
  ⚠️ **새 마이그레이션을 만들 때 `ls db/migrations/` 로 최신 번호를 먼저 본다.**
  `tools/test_account_e2e.py` 처럼 `V15__` 접두사로 찾는 코드가 있어서 공존하면 조용히
  엉뚱한 걸 집는다.
- ⚠️ **`ts_hour` 는 윈도우 시작, 파일명은 윈도우 끝이다.** 윈도우 19:00 을 받으려면
  파일은 `-200000` 이다. 내가 이걸로 한 번 헛돌았다(404 를 "상류 지연" 으로 볼 뻔했다).
- ⚠️ **AQS 는 동시 8 요청에서 429 를 내고 그게 빈 응답처럼 보인다.** 1,868건 중 1,665건이
  "데이터 없음" 으로 돌아왔는데 재시도(worker 3 + 백오프)하니 실제 404 는 **0건**이었다.
- ⚠️ **상류 시간별 덤프가 또 늦다.** 2026-09-22 23:03 UTC 기준 마지막 공개가
  `-190000`(21:14 게시)이고 다음 파일이 상한(윈도우 끝+153분)을 30분 넘겼다. 완전 정지
  (`-200`)와는 다르지만, 자동 적재 재개는 그게 나온 뒤다. 판정 한 줄은 09-22 문서 §0.

---

## 4. 어젯밤 머지된 것

| MR | 내용 |
| --- | --- |
| `!177` | `-194` 클러스터 루프가 `-161` 인자 검증에 걸려 21시간 죽어 있던 것 |
| `!179` | `-210` 근거 스크립트 (`ai/spec-evidence/gate-review/`) |
| `!181` | `-210` V16 모바일 몫 적재 (**관문 변경은 되돌렸다** — 09-22 문서 §0-B) |
| `!182` | `-210` 재개 문서 |
| `!183` | `-212` 하한 적재 + 기준선 드라이버 (**노브 기본 꺼짐**) |
| `!184` | `-210` 마이그레이션 번호 V15 → V16 |

Jira: `-194`·`-200` 완료 · `-210`(관문 재검토, 결론 코멘트 있음)·`-212` 진행 중.

---

## 5. 서버에 손으로 올린 것 (CI 대상 아님)

🔴 **`data-pipeline` 은 CI 배포 대상이 아니다.** 서버 bind mount
(`/home/ubuntu/wikipulse-local-test/data-pipeline`)에서 코드를 읽는다.

2026-09-22 22:49 UTC 에 5개 파일 복사 (md5 로컬 = 서버 = 컨테이너 일치 확인):
`batch/pageview_hourly.py` · `batch/pageview_hourly_ingest.py` ·
`spike/baseline_from_views.py` · `spike/baseline_rows.py` · `spike/live_cycle.py`

백업: 같은 디렉터리의 `*.bak-212-20260922-224951`

되돌리기(하한 적재 끄기) — 환경변수만 빼고 재생성한다:

```bash
ssh app-server -o BatchMode=yes 'sudo docker rm -f wikipulse-live-cycle && \
  sudo docker run -d --name wikipulse-live-cycle --restart unless-stopped \
  --network postgres_default -w /opt/app \
  -v /home/ubuntu/wikipulse-local-test/data-pipeline:/opt/app \
  -e DATABASE_URL=postgresql://<user>:<pw>@postgres:5432/wikipulse \
  -e CONTACT_EMAIL=wikipulse@example.com \
  wikipulse-spark-standalone:local python3 -m spike.live_cycle --loop \
  --interval 300 --cache /opt/app/data/live-cache --out /opt/app/data/live-pageview'
```

⚠️ `live-cluster` 도 수동 `docker run` 이고 `CLUSTER_FETCH_LINKS=1`·`CONTACT_EMAIL` 이
붙어 있다 — 재생성 명령은 09-22 문서 §3-1 에 있다. **`-196` 으로 compose 인수인계할 때
이 환경변수들을 빠뜨리면 조용히 원래대로 돌아간다.**
