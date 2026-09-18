# EC2 인프라 점검·변경 인계서 — 2026-09-17

- 점검 시간: **2026-09-17 18:12~18:30 KST**
- 대상: 기본 EC2 `wikipulse.example.com`, 추가 EC2 `data.wikipulse.example.com`
- 원칙: 설치·설정·방화벽·서비스 재시작 없이 기존 구성의 상태와 최소 쓰기 경로만 검증
- 관련 실행서: [mvp-validation-runbook.md](mvp-validation-runbook.md)

## 1. 인계 요약

서버 설정과 실행 중인 서비스를 바꾸지 않았다. 다음 네 가지 최소 쓰기 검증만 사용자 승인 후
실행했다.

1. Kafka `wiki.edits`에 봇으로 표시한 smoke 이벤트 1건 발행·직접 읽기
2. Spark 2 Worker 제한 작업으로 HDFS Parquet 20행 쓰기·재조회 후 임시 경로 삭제
3. PostgreSQL 임시 테이블 쓰기·조회 후 `ROLLBACK`
4. 사용자 승인 범위에서 2025-06-12 원시 신호를 PostgreSQL에 멱등 적재

영구적으로 남은 것은 **Kafka smoke 이벤트 1건**과 승인된 **2025-06-12 PostgreSQL 원시
신호**다. HDFS 임시 출력과 임시 파일은 제거됐고, Spark 애플리케이션 기록과 worker 로그는
현재 cleanup TTL에 따라 잠시 남을 수 있다.

## 2. 현재 구성 실측

| 항목 | 기본 EC2 | 추가 EC2 | 판정 |
| --- | --- | --- | --- |
| 자원 | 4 vCPU, 15 GiB RAM, 309 GB | 동일 | 정상 |
| 18:29 KST 가용 RAM | 13 GiB | 12 GiB | 정상 |
| 루트 디스크 | 11 GB 사용, 299 GB 가용 | 9.9 GB 사용, 300 GB 가용 | 정상 |
| UFW | active | active | 정상, 변경 없음 |
| HDFS | DataNode | NameNode + DataNode | 2 live, 복제 2, 손상·누락 0 |
| Spark | Worker 2 core/4 GiB | Master + Worker 2 core/4 GiB | 2 workers ALIVE |
| Kafka | 없음 | KRaft broker/controller | healthy, `wiki.edits` 3 partitions |
| PostgreSQL | 17 + pgvector 0.8.6 | 없음 | healthy, 스키마 있음. 2025-06-12 `page_edit_window` 72,632행·`page_view_hourly` 61,197행, `spike` 0행 |
| Nginx | container, 80/443 | 없음 | HTTPS 200, 현재 정적 placeholder |
| Jenkins | inactive | inactive | MVP P0 아님 |
| 앱 포트 | 8080/5174/4174 listener 없음 | 동일 | Backend/Frontend 미배포 |

Compose 프로젝트는 `hdfs`, `wikipulse-spark`, `kafka`, `postgres`, `nginx`다. 설정은 서버의
`~/infra/*`에만 있으며 저장소에서 재현되지 않는다.

## 3. HDFS와 데이터 상태

- 용량: configured 617.86 GB, remaining 597.34 GB
- 사용: 논리 1.7 GiB, 복제 포함 3.4 GiB
- `fsck /wikipulse`: HEALTHY, 104 files/blocks, 평균 복제 2.0
- 저장 내용:
  - `mediawiki_history`: 2024-10, 2025-06 표본
  - `pageview_complete`: 2025-06-12·13·14·16·20 표본
  - `/wikipulse/raw/gdelt`: 디렉터리만 확인
- **고정 MVP 구간 2026-07-17~09-17 원본은 확인되지 않았다.**

2개월 원본을 올리기 전에 소스별 날짜 카탈로그·체크섬·예상 용량을 제출하고 승인을 받아야
한다. 기존 표본을 삭제하거나 덮어쓰지 않는다.

## 4. Kafka smoke 기록

실행 전 offset:

```text
wiki.edits:0:0
wiki.edits:1:0
wiki.edits:2:0
```

실행 후 offset:

```text
wiki.edits:0:0
wiki.edits:1:0
wiki.edits:2:1
```

영구 잔여 이벤트:

```text
partition=2
offset=0
key=enwiki:__WIKIPULSE_SMOKE_20260917T092558Z__
title=__WIKIPULSE_SMOKE_20260917T092558Z__
source=ec2-smoke
is_bot=true
```

Kafka는 개별 레코드 삭제를 지원하지 않으므로 이 이벤트는 retention까지 남는다. 실제 소비자는
기존 계약대로 `is_bot=true`를 이슈 판정에서 제외해야 한다. smoke 레코드 하나를 지우기 위해
토픽 삭제나 retention 변경을 하지 않는다. consumer group은 생성되지 않았다.

## 5. Spark/HDFS smoke 기록

### 첫 시도 — 검증 명령 오류, 서버 설정 문제 아님

- 앱 ID: `app-20260917092119-0006`
- 내가 제출 명령에서 Driver용 7080을 `spark.blockManager.port`로 지정해 executor에도 적용함
- 추가 EC2에서 Driver와 executor가 7080을 함께 사용해 `Address already in use` 발생
- timestamp를 잘못 이스케이프해 경로가 문자 그대로
  `/wikipulse/spark/_mvp_verify_${stamp}`로 생성됨
- 생성된 HDFS 경로와 `/tmp/wikipulse_mvp_smoke_${stamp}.py`는 이후 정확히 확인하고 삭제
- 설정 파일, UFW, Compose, 실행 서비스는 변경하지 않음

### 두 번째 시도 — PASS

- 앱 ID: `app-20260917092619-0007`
- 제한: total executor cores 2, executor core 1, executor memory 1 GiB, driver 512 MiB
- 기존 `spark-defaults.conf`의 포트 분리 사용:
  - Driver RPC 7079
  - Driver BlockManager 7080
  - executor BlockManager 7100
- Worker 참여:
  - `10.0.0.11`
  - `10.0.0.12`
- Parquet 20행 쓰기 후 `HDFS_ROUNDTRIP_COUNT=20`
- 임시 경로 `/wikipulse/spark/_mvp_verify_20260917T092613Z` 삭제 확인
- 최종 상태: Spark ALIVE, workers 2, active apps 0

`spark.worker.cleanup.appDataTtl=86400`이므로 앱 로그는 최대 하루가량 보일 수 있다. 이것은 데이터
파이프라인 산출물이 아니며 임의로 worker work 디렉터리를 지우지 않는다.

## 6. PostgreSQL smoke 기록

- DB: PostgreSQL 17.11, database `wikipulse`, application user `usera609`
- extension: `vector=0.8.6`
- `db/initdb/V1~V6`에 해당하는 핵심 테이블이 존재
- canary 전 `pg_stat_user_tables` 추정치는 모든 사용자 테이블이 0행이었고, 핵심 `issue_cluster` 정확 조회도 0행이었다
- transaction 안에서 temporary table 생성, 1행 삽입·조회 후 `ROLLBACK`
- `rolled_back = true`, `issue_cluster` 영구 행 수 `0 → 0`
- 이후 사용자 승인으로 2025-06-12 원시 신호를 적재했다. 정확 조회는 `page_edit_window=72,632`, `page_view_hourly=61,197`, `spike=0`이며 같은 입력 재실행 후에도 불변이다

비밀번호와 `.env` 내용은 출력하거나 저장소에 기록하지 않았다.

## 7. 서비스 노출 상태

- `https://wikipulse.example.com/`는 HTTP 200
- 응답 본문은 `WikiPulse / nginx ok` 정적 placeholder
- PostgreSQL은 외부 포트로 공개되지 않음
- HDFS/Spark UI는 localhost 또는 내부망으로 제한
- Backend·Frontend 프로세스와 앱 포트 listener 없음

따라서 HTTPS가 열린 것을 서비스 배포 완료로 해석하면 안 된다.

## 8. 인프라 담당에게 요청할 변경 후보

아래는 **이번 세션에서 적용하지 않았다.** 적용 전 별도 승인과 리뷰가 필요하다.

| 우선순위 | 변경 후보 | 이유 | 안전장치/복구 |
| --- | --- | --- | --- |
| P0 | `~/infra/*`의 비밀값 없는 compose·설정을 저장소 관리 | 현재 서버를 다시 만들 수 없음 | `.env` 제외, 버전 pin, `docker compose config` 검증 |
| P0 | Backend·Frontend 배포 compose와 Nginx upstream 작성 | 현재 placeholder만 노출 | 기존 Nginx 설정 백업, health 통과 뒤 reload, 실패 시 즉시 원복 |
| P0 | Spark Python/DB sink 호환 해결 | 이미지 Python 3.8.10에서 `psycopg 3.3.5` 설치 불가 | Python 3.11 Spark 이미지 또는 sink 분리 비교, canary 후 채택 |
| P0 | 2개월 HDFS 적재 계획 | 현재 2025년 표본뿐 | 날짜 batch, checksum, 복제 확인, 가용 150 GB 하한 |
| P0 | DB migration·전체 구간 적재 절차 | 1일 canary만 있으며 2개월 적재·복구 절차는 없음 | 백업, migration checksum, 날짜별 적재, 멱등 재실행 |
| P1 | LIVE producer/consumer의 Compose·checkpoint·restart 정책 | Kafka에 실제 이벤트·consumer가 없음 | smoke topic/기간, lag 계측, 중지·복구 명령 |
| P1 | 상태·용량 모니터링 | t3 credit과 장기 처리 위험 | CPU/RAM/disk/Kafka lag/마지막 snapshot 경보 |
| P2 | Jenkins | 자동 배포 편의 | MVP 핵심 흐름 완료 뒤 도입 |

Redis·추가 포트·UFW 규칙은 구체적인 소비자가 생기기 전에는 추가하지 않는다.

## 9. 변경 승인 요청 양식

```text
목적:
대상 서버/서비스:
실행 명령 또는 변경 diff:
예상 CPU/RAM/디스크/시간:
사용자 영향:
중단 기준:
복구 명령과 예상 복구 시간:
남는 데이터·로그:
검증 방법:
```

위 양식 승인 없이 패키지 설치, 설정 수정, 서비스 재시작, 방화벽 변경, 대량 데이터 적재를
진행하지 않는다.

## 10. 골든 데이 원시 신호 적재

사용자 승인 후 2025-06-12 UTC 실제 원본을 Spark 2 Worker로 집계해 기본 EC2
PostgreSQL에 적재했다. `wiki_page` 자연키 60,412개, `page_edit_window` 72,632행,
`page_view_hourly` 61,197행이며 같은 입력 재적재 후 행 수가 동일했다. 기준선이 없어
`spike`는 0행을 유지했다. 실행 근거와 정리 결과는
[골든 데이 검증 보고서](golden-day-validation-2025-06-12.md)에 있다.
