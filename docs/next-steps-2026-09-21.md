# 이어서 하기 (2026-09-21 기준)

**다른 PC에서 다시 붙잡을 때 처음 읽는 문서다.** 순서·명령·막힐 지점만 적는다.
진행 상황은 Jira 가 정본이라 여기 적지 않는다.

~~[next-steps-2026-09-19](next-steps-2026-09-19.md)~~ → 이 문서가 대신한다 (2026-09-21).
그 문서의 "§1 LIVE 결과를 DB 까지" 는 **WP-143 이 막고 있어** 순서가 바뀌었다.

한 줄 요약: **화면에 실데이터가 떴다. 이제 막힌 건 남의 작업 두 개와 크레딧이다.**

## 0. 상태 복구 (10분)

```
git checkout develop && git pull --ff-only
```

서버는 읽기만 하는 확인이다.

```bash
ssh app-server  -o BatchMode=yes "sudo docker ps --format '{{.Names}}|{{.Status}}'"
ssh data-server -o BatchMode=yes "sudo docker ps --format '{{.Names}}|{{.Status}}'"
```

화면이 살아 있는지는 이 한 줄로 본다 — 0 이 아니어야 한다.

```bash
curl -s "https://wikipulse.example.com/api/v1/issues?size=1" | head -c 200
```

## 1. 🔴 이 PC 에만 있는 것 — 새 PC 에서 다시 만들어야 한다

2026-09-20 작업은 **bjs0306b 개인 PC**에서 했다. 아래는 저장소에 안 들어가므로 따라오지 않는다.

| 항목 | 위치 | 다시 만드는 법 |
| --- | --- | --- |
| **SSH 키·config** | `~/.ssh/wikipulse-key.pem`, `~/.ssh/config` | §1-1 |
| **개인 도구 권한 규칙** | `개인 도구 설정 파일` (gitignore) | §1-2 |
| **GitLab PAT** | 환경변수 `GITLAB_MCP_TOKEN` | 개인 발급 (`개인 지침 문서`) |
| **Docker Desktop** | 프로그램 | §1-3 |
| **로컬 `.env`** | 저장소 루트 (gitignore) | `cp .env.example .env` |
| GDELT 원본 2025-06-12 | 임시폴더 627 MB | 필요하면 다시 받는다(§3-2). **서버에는 이미 있다** |

⚠️ **서버 쪽 상태는 따라온다.** EC2 의 DB·`infra/`·`.env`(GMS 키 포함)는 그대로다.
다시 할 필요 없다.

### 1-1. SSH

운영기관 가 준 `wikipulse-key.pem` + `init EC2-SSH.bat`(기본) / `init EC2-SSH2.bat`(추가)를 받아
**배치를 그냥 실행**하면 된다. 별칭이 `app-server`(기본·서비스) / `data-server`(추가·데이터)로 잡힌다.

⚠️ 배치를 **두 번 돌리면 `~/.ssh/config` 에 같은 Host 블록이 중복**된다. 이미 있으면 건너뛴다.

⚠️ **Git Bash 의 ssh 는 Windows `~/.ssh/config` 를 못 읽는다** (2026-09-20 실측).
`Could not resolve hostname app-server` 가 나오면 그 이유다 — **PowerShell 에서 실행한다.**

⚠️ `config` 파일 권한이 느슨하면 `Bad owner or permissions` 로 거부된다. pem 뿐 아니라
**config 도** 상속을 끊고 본인만 FullControl 로 둔다.

### 1-2. 개인 도구 권한 규칙

EC2 명령이 `Production Deploy`·`Modify Shared Resources` 로 막힌다. 개인용 파일에 둔다
(🔴 커밋되는 `공용 도구 설정 파일` 에 넣지 말 것 — 팀 전체에 운영 배포 권한이 생긴다).

`개인 도구 설정 파일`:

```json
{
  "permissions": {
    "allow": ["Bash(ssh app-server*)", "PowerShell(ssh app-server*)"]
  }
}
```

⚠️ **옵션을 호스트 뒤에 쓴다** — `ssh app-server -o BatchMode=yes "..."`. 규칙이 접두사
매칭이라 `ssh -o ... app-server` 형태는 안 걸린다.

⚠️ **scp 는 허용 목록에 없다.** 파일은 base64 로 ssh 에 실어 보낸다 — CRLF·BOM 훼손도
같이 피할 수 있다(아래 함정 참고).

### 1-3. Docker

`winget install Docker.DockerDesktop` → **재부팅** → `wsl --update` →
🔴 `com.docker.service` 를 `Automatic` 으로 기동(관리자 필요). 상세·함정은
`개인 지침 문서` 의 "Docker 설치에서 실제로 걸린 것".

## 2. 어디까지 됐나 (2026-09-20)

운영 EC2 가 그날 아침 **전 테이블 0행**이었는데:

```
stock          5,396 (설명 5,311 · 임베딩 5,311, 1536차원)   WP-147
spike          4,474 (문서 2,238)                            WP-149
issue_cluster  4,474 (스냅샷 24)                             WP-149
cluster_stock    110 (검증 통과 3)                            WP-149
```

화면(`/issues`)에 `Air India Flight 171` 10.1 · 관련 종목 2(**BA Boeing** · YTRA)가 뜬다.
`수집 → 판정 → 클러스터 → GKG 술어 → 후보 → LLM 검증 → 종목 → 화면` 이 관통했다.

근거: [골든데이 운영 적재](validation/2026-09-20-golden-day-prod.md) ·
[GKG 술어 검증](validation/2026-09-20-cluster-gkg-predicate.md)

### 현재 워커 설정 (EC2 `infra/service/.env`)

```
WIKIPULSE_MATCHING_SCHEDULER_ENABLED=false     ← 5개 처리 후 껐다
WIKIPULSE_MATCHING_VERIFICATION_ENABLED=true
WIKIPULSE_MATCHING_SUMMARY_ENABLED=false       ← 🔴 켜지 말 것, §3-1
WIKIPULSE_MATCHING_*_BATCHSIZE=5
```

## 3. 다음 작업 후보

### 3-1. 🔴 요약 워커 범위 제한 — 이게 없으면 요약을 못 켠다

`IssueSummaryRepository` 의 선택 조건이 `status IN ('DETECTED','VERIFYING')` **뿐**이라
후보 워커의 `NOT EXISTS cluster_stock` 같은 완료 표시가 없다. 미처리 4,474개를 전부 훑어
**약 277,000 크레딧**이 든다(잔액 88,935).

→ 범위를 좁힐 수단을 먼저 만든다. 그 전까지 `SUMMARY_ENABLED=false` 를 유지한다.
그래서 지금 화면은 한국어 요약이 없고 상태가 전부 `AI 검증 전`(DETECTED)이다.

### 3-2. 나머지 클러스터 GKG

`gkg/driver.py` 를 돌린 건 상위 2개(`Air India Flight 171`·`Air India`)뿐이다. 나머지는
임베딩 단독 후보다. GDELT 2025-06-12 원본은 **서버에 이미 있다**
(`/home/ubuntu/infra/stock/gdelt-data/2025/06/12`, 87/96 슬롯).

```bash
# 서버에서. 🔴 spark-submit 이 아니라 python -m 이다 (상대 임포트)
sudo docker run --rm --network wikipulse-net -m 5g \
  -v /home/ubuntu/infra/stock/app:/opt/app \
  -v /home/ubuntu/infra/stock/gdelt-data:/gdelt:ro \
  -e DATABASE_URL="$DSN" -e PYTHONPATH=/opt/app -w /opt/app wikipulse-spark:local \
  python -m gkg.driver --cluster-id <ID> --start 20250612000000 --end 20250612234500 \
    --base-dir /gdelt --min-issue-count 50 --top 200
```

⚠️ **`--min-issue-count` 를 기본값 3 으로 두지 말 것.** 하루 규모 코퍼스에서는 이슈
기사에만 나오는 희귀 기관이 최대 lift 로 상위를 독식해 **Boeing 이 top 30 밖으로 밀린다**
(2026-09-20 실측). 50 으로 올리자 `BA 13.86` 이 1위로 올라왔다.

### 3-3. LLM 비용 줄이기

프롬프트 캐싱은 **GMS 에서 되레 25% 비싸다** — 쓰기만 되고 읽기가 안 된다
([근거](validation/2026-09-20-gms-prompt-cache.md)). 다시 시도하려면 `cache_read_input_tokens`
가 차는지부터 재고 넣는다.

남은 수단(미검증): 후보를 묶어 한 호출로(호출 수 1/5~1/10) · 1차 필터를 소형 모델로 ·
`embedding-top-k: 20` → 10.

## 4. 막힌 것 — 남의 작업이다

| 이슈 | 담당 | 내용 |
| --- | --- | --- |
| WP-143 | LYJ22 | 데이터 EC2 → 서비스 EC2 `5432` 가 UNREACHABLE. 이게 풀려야 LIVE `SINK=spike` 가 된다 |
| WP-137 | sangeune | 2026-07-17~09-17 실제 원본 replay. 데이터 EC2 에 115 GB 진행 중 |

💡 **-143 에 전할 실측**: 서비스 EC2 → 데이터 EC2 **Kafka 9092 는 열려 있다**(2026-09-20).
막힌 건 반대 방향 5432 뿐이다. Spark 드라이버를 서비스 EC2 에서 돌리면 Kafka 는 나가서 읽고
DB 는 로컬로 쓰므로 **-143 없이도 LIVE 가 될 수 있다.**

## 5. ⚠️ 이 데이터의 한계 — 시연 전에 알아야 한다

- **급증 4,474 는 "진짜 급증" 이 아니다.** `page_baseline` 이 0이라 전부 절대 하한
  (조회수 100 이상)만으로 판정됐다. 제대로 하려면 28일치 과거가 필요한데 운영엔 하루뿐이다.
- **멤버가 전부 1개다.** Clickstream 2025-06 덤프가 없어 씨드 단독이고 버블맵 간선이 0이다.
- **상태가 전부 `DETECTED`** — §3-1 때문이다.

## 6. 함정 (2026-09-20 에 실제로 물린 것)

- 🔴 **`spark-submit gkg/driver.py` 는 안 돈다.** 상대 임포트라 `python -m gkg.driver` 여야 한다.
  docstring 이 틀려 있었고 CLI 테스트가 없어 아무도 몰랐다.
- 🔴 **`data-pipeline/Dockerfile` 에 COPY 를 빠뜨리기 쉽다.** `spike`(-135)·`stock`(-147)·
  `cluster`(-149) 가 차례로 같은 이유로 운영에서 죽었다. **모듈을 새로 만들면 COPY 를 더하는
  것까지가 그 작업이다.**
- ⚠️ **EC2 `infra/` 는 저장소와 자동 동기화되지 않는다.** 2026-09-20 에 배포본이 저장소보다
  낡아 `SUMMARY_ENABLED` 가 아예 없었다.
- ⚠️ **PowerShell here-string 은 CRLF·BOM 을 남긴다.** 원격 bash 에서 `set: +: invalid option`
  이나 `tail: invalid number of lines: '25\r'` 로 터진다. base64 로 보내면 안 만난다.
- ⚠️ **백엔드 재기동 시 `BACKEND_IMAGE` 를 준다.** compose 기본값이 `:latest` 인데 서버엔
  SHA 태그만 있어 pull 이 실패한다(무중단이긴 하다). 돌고 있는 태그를 그대로 쓴다:
  `sudo BACKEND_IMAGE=$(sudo docker inspect service-backend-1 --format '{{.Config.Image}}') docker compose up -d --force-recreate backend`
