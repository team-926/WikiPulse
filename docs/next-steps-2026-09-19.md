# 이어서 하기 (2026-09-19 기준)

**다시 붙잡을 때 처음 읽는 문서다.** 순서·명령·막힐 지점만 적는다. 진행 상황은 Jira 가
정본이라 여기 적지 않는다 — 두 곳에 상태를 적으면 반드시 한쪽이 틀어진다.

한 줄 요약: **수집은 돌고 있는데, 그 결과가 화면까지 오는 선이 아직 안 이어졌다.**

## 0. 상태 복구 (5분)

저장소:

```
git checkout develop && git pull --ff-only
```

서버 두 대. 읽기만 하는 확인이다.

```bash
# 데이터 EC2 — Kafka · Spark master · HDFS NameNode · LIVE 파이프라인
ssh -i wikipulse-key.pem ubuntu@data.wikipulse.example.com "sudo docker ps --format '{{.Names}}|{{.Status}}'"

# 서비스 EC2 — Nginx · Spring · PostgreSQL · CI 러너 · Spark worker
ssh -i wikipulse-key.pem ubuntu@wikipulse.example.com  "sudo docker ps --format '{{.Names}}|{{.Image}}|{{.Status}}'"
```

LIVE 파이프라인이 살아 있는지는 이 둘로 본다 — 커서 파일 mtime 과 Spark batch 번호가
올라가고 있으면 정상이다.

```bash
ssh -i wikipulse-key.pem ubuntu@data.wikipulse.example.com \
  "stat -c '%y' /home/ubuntu/infra/pipeline/state/last-event-id; \
   sudo docker logs --since 3m wikipulse-edit-stream 2>&1 | grep -a -o 'Batch: [0-9]*' | tail -1"
```

## 1. 다음 작업 — LIVE 결과를 DB 까지 보내기

지금 Spark 집계는 `SINK=console` 이라 로그로만 나가고 어디에도 안 쌓인다. 이게 막힌 채로는
뒤쪽(클러스터·매칭·API)이 무엇을 고쳐도 화면에 실데이터가 안 보인다. 그래서 여기가 먼저다.

### 1-1. Spark 실행 이미지를 파이썬 3.11 로 — Driver 와 Worker **동시에**

이미지는 이미 있다: `docker/spark/Dockerfile` (python 3.11 + JRE 17 + `pyspark 3.5.3` +
`psycopg[binary] 3.3.5`). 공식 `apache/spark:3.5.3-python3` 의 파이썬이 3.8.10 이라
`psycopg` 가 안 깔리고, 그래서 `SINK=spike` 경로가 아예 실행되지 않았다 (WP-136).

로컬에서 먼저 돌려 본다.

```bash
docker compose --profile pipeline build spark
SPARK_SINK=spike docker compose --profile pipeline up -d spark
```

EC2 에서 바꿀 곳은 **두 군데이고 같이 바꾼다.**

| 파일 | 지금 값 | 바꿀 대상 |
| --- | --- | --- |
| `infra/spark/compose.yaml` | `image: apache/spark:3.5.3-python3` | Master·Worker |
| `infra/pipeline/compose.yaml` | `image: apache/spark:3.5.3-python3` | `edit-stream` Driver |

🔴 **한쪽만 올리면 파이썬 워커가 뜨는 순간 executor 가 죽는다.** 지금은 둘 다 3.8 이라
짝이 맞는 상태다 — 짝을 깨는 순간이 위험하다.

### 1-2. `SINK=spike` 로 바꿀 때 같이 해야 하는 것

코드를 읽어 확인한 것이다. 환경변수만 바꾸면 안 된다.

1. **`DATABASE_URL` 이 필요하다.** 없으면 기동 시 바로 멈춘다 (`streaming/edit_windows.py`).
2. ⚠️ **마운트를 넓혀야 한다.** 지금 `infra/pipeline/compose.yaml` 은
   `${PIPELINE_APP_DIR}/streaming:/opt/app/streaming` 만 올린다. 그런데 `SINK=spike` 는
   `streaming.live_spike` 와 `spike.runtime` 을 import 하므로 `/opt/app` 아래에 `spike/` 도
   있어야 한다. 콘솔 싱크는 이 파일 밖을 import 하지 않아서 여태 안 드러났다
   (`ensure_project_root_on_path` 주석, 2026-09-15 컨테이너 실측).
3. ❓ **미확인 — 네트워크.** PostgreSQL 은 서비스 EC2 에 있고 `edit-stream` 은 데이터 EC2 에서
   돈다. 사설망으로 5432 에 닿는지, UFW 가 막는지 확인한 적이 없다. **여기부터 확인하고
   나서** 싱크를 바꾼다 — 안 닿으면 "어디서 적재할지"가 먼저 정해져야 한다.

### 1-3. 됐는지 보는 법

로그가 아니라 **행으로** 본다.

```sql
SELECT count(*), max(detected_at) FROM spike WHERE source = 'live';
```

### 1-4. `live-cycle` 을 EC2 에 배선

시간별 조회수 적재·재판정 주기(WP-135)가 저장소 루트 `docker-compose.yml` 에만 있고
`infra/` 에 없다. 같은 이름 서비스를 참고해 옮긴다.

## 2. 그다음 — E2E 의 끊긴 고리 4개

[로컬 파이프라인 최종 게이트](validation/2026-09-18-local-pipeline-gate.md)가 "데이터를 더
실험할 단계가 아니라 없는 연결을 구현할 단계"로 판정했다. 그 넷이다.

| 구멍 | 지금 상태 |
| --- | --- |
| `cluster/driver.py:load_creation_dates` | `NotImplementedError` — 추가 씨드·비-seed 재급증 미구현 |
| 클러스터 → GKG 테마·지역 술어 변환 | 정의 안 됨 (다운로드·파싱·lift·writer 단위 경로는 있음) |
| 매칭·LLM 검증 워커 | 기본 OFF 이고 Compose 가 GMS·워커 환경변수를 backend 에 전달하지 않음 |
| 1일 E2E 수동 bridge 2개 + 시점 정합성 | 사람이 손으로 이어야 통과한다 |

## 3. 배포 — 지금은 정상, 대신 두 가지를 기억한다

2026-09-19 에 두 겹으로 막혀 있던 것을 풀었고 실제로 한 번 끝까지 배포됐다.

⚠️ **`deploy:backend` 는 아무 때나 안 생긴다.** `backend/**`, `db/migrations/**`,
`.gitlab-ci.yml` 이 바뀐 develop 머지에서만 만들어진다. 그 밖의 변경을 배포하려면 develop 에서
**Run pipeline 수동 실행**. 이때 `deploy:frontend` 도 같이 돈다.

⚠️ **실패한 옛 잡 Retry 는 그때 그 커밋으로 돈다.** 고친 코드를 반영하려면 새 파이프라인이어야
한다. 이걸 모르고 Retry 하면 같은 자리에서 또 멈춘다.

막혔던 둘은 이렇게 풀렸다 — 다시 터지면 여기부터 본다.

- 러너가 `infra/db/.env` 를 못 읽던 문제 → [infra/README](../infra/README.md) "배포 러너 권한"
- 원장 체크섬이 CRLF 로 심겨 갈라진 문제 → 코드가 스스로 정규화한다. 팀원 로컬 DB 도 자동 수습

## 4. 아직 증명되지 않은 것

있는 줄 알고 넘어가면 나중에 비싸게 드러난다.

- **빈 `meta_id` 거부**는 로컬 테스트로만 증명됐다. 실데이터가 그 경로를 탄 적은 없다.
- **Kafka `wiki.edits` 는 3 partitions · replication 1.** broker 장애 내성이 없다.
- **checkpoint state 증가 속도**를 장시간 본 적이 없다 (15분에 7.36 → 16.73 MiB 가 전부).
- **28일 기준선 품질**과 LIVE scheduler 는 미검증.
- `deploy:backend` 성공은 아직 **1회**다.

## 5. 손대기 전에 확인이 필요한 것

로컬 작업 폴더에 커밋되지 않은 채 남아 있다. 확인 없이 커밋하면 의도가 섞이고, 지우면 복구가
안 된다.

| 위치 | 남은 것 |
| --- | --- |
| `_verification/mvp-ec2-validation` | 변경 69개 + develop 에 없는 커밋 3개 (`-120` 명세 v0.3, `-118` spike 설계·계획) |
| `.worktrees/doc-consistency-fix` | 변경 25개 (docs 12, data-pipeline 4 …) |
| stash `codex-doc-consistency-rebase` | 그대로 |

## 6. Jira 정리 거리

- **WP-121 "인프라 설정 파일 저장소 백업"** 은 `-133` 이 `infra/*` 를 저장소로 옮기며
  사실상 끝난 것으로 보인다. 중복인지 확인하고 닫거나 남은 범위를 좁힌다.
- **WP-137 실제 원본 Historical Replay** 는 진행 중이고 §1·§2 와 독립이라 병행 가능하다.
