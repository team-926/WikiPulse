# 다음 할 일 (2026-09-19 기준)

진행 상황은 **Jira 보드**가 정본이다. 이 문서는 *무엇을 먼저 하고 왜 그 순서인지*, 그리고
*어디까지 확인됐고 어디부터 미확인인지*만 적는다. 작업이 끝나면 여기가 아니라 Jira 를
옮긴다 — 두 곳에 상태를 적으면 반드시 한쪽이 틀어진다.

## 0. 지금 서 있는 자리

| 경로 | 상태 | 근거 |
| --- | --- | --- |
| EventStreams → Kafka → 2노드 Spark → HDFS checkpoint | **가동 중**, 재시작 복구 확인 | [LIVE 1차 배포 검증](validation/2026-09-18-live-pipeline-phase1.md) |
| Spark 집계 결과 → PostgreSQL | **끊겨 있음** (`SINK=console`) | 같은 문서 §9 · [infra/README](../infra/README.md) |
| 배포 파이프라인 `deploy:backend` | **복구됨** (2026-09-19 #208015 통과) | 아래 §3 |
| 하루치 E2E `원본 → spike → cluster → AI → API` | PARTIAL — 수동 bridge 2개 | [1일 E2E canary](validation/2026-09-18-one-day-e2e-canary.md) |

한 줄로 줄이면: **수집은 돌고 있는데, 그 결과가 화면까지 오는 선이 아직 안 이어졌다.**

## 1. 가장 먼저 — LIVE 결과를 DB 까지 보내기

이게 막혀 있는 한 나머지는 데모에 보이지 않는다. 순서가 정해져 있다.

1. **Spark 실행 이미지를 파이썬 3.11 로 올린다** (`docker/spark/Dockerfile`, WP-136).
   🔴 **Driver 와 Worker 를 동시에** 바꾼다. 한쪽만 올리면 파이썬 워커가 뜨는 순간 executor 가
   죽는다. 바꿀 대상에 `infra/pipeline` 의 `edit-stream` 이 포함된다 — 지금 Worker 와 같은
   `apache/spark:3.5.3-python3`(파이썬 3.8) 을 쓰고 있어 현재는 짝이 맞는 상태다.
2. **`SINK` 를 `spike` 로 바꾼다.** 파이썬 3.8 에서는 `psycopg 3.3.5` 가 안 깔려 이 경로가
   아예 실행되지 않았다. 그게 LIVE 입구가 막혀 있던 이유다.
3. **실제로 행이 쌓이는지 본다.** console 출력이 아니라 `spike` 테이블 행 수·시각으로 확인한다.
4. **`live-cycle` 서비스를 EC2 compose 에 넣는다.** 시간별 조회수 적재·재판정 주기
   (WP-135)가 저장소 루트 `docker-compose.yml` 에만 있고 `infra/` 에 없다.

## 2. 그다음 — E2E 의 끊긴 고리 메우기

[로컬 파이프라인 최종 게이트](validation/2026-09-18-local-pipeline-gate.md)가 "데이터를 더
실험할 단계가 아니라 없는 연결을 구현할 단계"라고 판정했다. 그 연결이 넷이다.

| 구멍 | 지금 상태 |
| --- | --- |
| `cluster/driver.py:load_creation_dates` | `NotImplementedError` — 추가 씨드·비-seed 재급증 미구현 |
| 클러스터 → GKG 테마·지역 술어 변환 | 정의 안 됨 (다운로드·파싱·lift·writer 단위 경로는 있음) |
| 매칭·LLM 검증 워커 | 기본 OFF 이고, Compose 가 GMS·워커 환경변수를 backend 에 전달하지 않음 |
| 1일 E2E 의 수동 bridge 2개 + 시점 정합성 | 사람이 손으로 이어야 통과한다 |

## 3. 배포 — 지금 상태와 트리거 조건

2026-09-19 에 두 겹으로 막혀 있던 것을 풀었다.

- `gitlab-runner` 가 `/home/ubuntu/infra/db/.env` 를 못 읽던 문제 (WP-139).
  요구 상태와 명령은 [infra/README](../infra/README.md) "배포 러너 권한" 절에 있다.
- 원장 체크섬이 Windows 체크아웃(CRLF)에서 심겨 리눅스 CI 와 갈라진 문제 (WP-140).
  코드가 스스로 정규화해 고쳐 적으므로 **팀원 로컬 DB 도 다음 실행에서 자동 수습된다.**

⚠️ **`deploy:backend` 는 아무 때나 돌지 않는다.** `backend/**`, `db/migrations/**`,
`.gitlab-ci.yml` 이 바뀐 develop 머지에서만 생성된다. 그 밖의 변경을 배포하려면 develop 에서
**Run pipeline 을 수동 실행**한다. 이때 `deploy:frontend` 도 함께 돈다.

⚠️ 실패한 옛 잡을 **Retry 하면 그때 그 커밋으로 돈다.** 고친 코드를 반영하려면 새 파이프라인을
돌려야 한다. 2026-09-19 에 이걸 모르고 Retry 했다면 같은 자리에서 또 멈췄을 것이다.

## 4. 아직 증명되지 않은 것 (있는 줄 알고 넘어가면 안 되는 것)

- **빈 `meta_id` 거부**는 로컬 테스트로만 증명됐다. 카나리 내내 파싱실패가 0이라 실데이터가
  그 경로를 실행한 증거는 없다.
- **Kafka `wiki.edits` 는 3 partitions · replication 1** 이다. broker 장애 내성이 없다.
- **checkpoint state 증가 속도**를 장시간 관찰한 적이 없다 (15분에 7.36 → 16.73 MiB 관측이 전부).
- **28일 기준선 품질**과 LIVE scheduler 는 미검증이다.
- `deploy:backend` 는 2026-09-19 에 처음 끝까지 성공했다. 반복 성공은 아직 한 번뿐이다.

## 5. 손대기 전에 확인이 필요한 파킹된 작업

로컬 작업 폴더에 **커밋되지 않은 채 남아 있는** 것들이다. 내용을 확인하지 않고 커밋하면 의도가
섞이고, 지우면 복구되지 않는다.

| 위치 | 남은 것 |
| --- | --- |
| `_verification/mvp-ec2-validation` | 변경 69개 + develop 에 없는 커밋 3개 (`-120` 명세 v0.3, `-118` spike 설계·계획) |
| `.worktrees/doc-consistency-fix` | 변경 25개 (docs 12, data-pipeline 4 …) |
| stash `codex-doc-consistency-rebase` | 그대로 |

## 6. Jira 정리 거리

- **WP-121 "인프라 설정 파일 저장소 백업"** 은 `-133` 이 `infra/*` 를 저장소로 옮기며
  사실상 끝난 것으로 보인다. 중복인지 확인하고 닫거나 남은 범위를 좁힌다.
- **WP-137 실제 원본 Historical Replay** 는 진행 중이며 위 §1·§2 와 독립이라 병행할 수 있다.
