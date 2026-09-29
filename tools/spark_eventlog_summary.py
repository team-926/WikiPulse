"""Spark 이벤트 로그 → Worker 별 태스크 분배·데이터 지역성·스테이지 시간 요약 (WP-233).

    python3 tools/spark_eventlog_summary.py <eventlog 파일>

`spark.eventLog.enabled=true` 로 남긴 JSON Lines 를 읽는다. 표준 라이브러리만 쓴다.

지역성(Locality) 뜻
    PROCESS_LOCAL  같은 executor 메모리 (캐시)
    NODE_LOCAL     같은 서버 디스크 — HDFS 블록이 그 서버 DataNode 에 있다
    RACK_LOCAL     같은 랙 다른 서버
    ANY            네트워크로 다른 서버에서 읽었다
    셔플 뒤 스테이지는 입력이 HDFS 가 아니라 NODE_LOCAL/ANY 해석이 다르다 — 스테이지별로 본다.
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict


def main(path: str) -> int:
    stages: dict[int, dict] = {}
    by_stage_host: dict[int, Counter] = defaultdict(Counter)
    by_stage_loc: dict[int, Counter] = defaultdict(Counter)
    app_start = app_end = None
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            ev = json.loads(line)
            kind = ev.get("Event")
            if kind == "SparkListenerApplicationStart":
                app_start = ev["Timestamp"]
            elif kind == "SparkListenerApplicationEnd":
                app_end = ev["Timestamp"]
            elif kind == "SparkListenerStageCompleted":
                info = ev["Stage Info"]
                stages[info["Stage ID"]] = {
                    "name": info["Stage Name"].split(" at ")[0],
                    "tasks": info["Number of Tasks"],
                    "ms": (info.get("Completion Time") or 0) - (info.get("Submission Time") or 0),
                }
            elif kind == "SparkListenerTaskEnd":
                task = ev["Task Info"]
                sid = ev["Stage ID"]
                by_stage_host[sid][task["Host"]] += 1
                by_stage_loc[sid][task["Locality"]] += 1

    if app_start and app_end:
        print(f"app wall = {(app_end - app_start) / 1000:,.1f}s")
    total_host: Counter = Counter()
    total_loc: Counter = Counter()
    for sid in sorted(stages):
        s = stages[sid]
        hosts = dict(by_stage_host[sid])
        locs = dict(by_stage_loc[sid])
        total_host.update(hosts)
        total_loc.update(locs)
        print(f"stage {sid:>3} {s['name'][:40]:<40} tasks={s['tasks']:>5} "
              f"{s['ms'] / 1000:>8.1f}s hosts={hosts} locality={locs}")
    print(f"total hosts={dict(total_host)} locality={dict(total_loc)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
