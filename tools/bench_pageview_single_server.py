"""단일 서버 기준선 — 로컬 파일을 `zcat | grep | aggregate` 로 N 프로세스 처리 (WP-235).

    python3 tools/bench_pageview_single_server.py --files-dir DIR --titles-root DIR --procs 4

replay 필터(`~/replay-sep/refilter-fast.py`)와 같은 경로다: 파일마다 `zcat | grep -E
'^en(\\.m)? '` 로 en 줄만 남기고 `pageview_hourly.aggregate(titles=그 시간 후보)` 로
합산한다. 쓰기는 하지 않는다(Spark 쪽 비교값은 쓰기를 포함하니 이쪽이 약간 유리하다).

⚠️ 09-23 replay 의 "시간당 5.3초(3프로세스)" 는 같은 서버에서 다른 무거운 작업 셋이
동시에 돌던 값이라 기준선으로 쓰지 않는다 — 같은 조건에서 다시 잰다.
"""

from __future__ import annotations

import argparse
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path


def one(task):
    path, titles_file = task
    from batch.pageview_hourly import aggregate, ts_hour_from_filename
    ts = ts_hour_from_filename(Path(path).name)
    tf = Path(titles_file)
    if not tf.exists():
        return 0
    titles = frozenset(line.strip() for line in tf.read_text(encoding="utf-8").splitlines()
                       if line.strip())
    proc = subprocess.Popen(f"zcat '{path}' | LC_ALL=C grep -E '^en(\\.m)? '", shell=True,
                            stdout=subprocess.PIPE)
    lines = (raw.decode("utf-8", errors="replace") for raw in proc.stdout)
    rows = sum(1 for _ in aggregate(lines, "enwiki", ts, titles=titles))
    proc.wait()
    return rows


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--files-dir", required=True)
    p.add_argument("--titles-root", required=True, help="<date>/<HH>.txt 루트")
    p.add_argument("--procs", type=int, required=True)
    a = p.parse_args()

    from batch.pageview_hourly import ts_hour_from_filename
    files = sorted(Path(a.files_dir).glob("pageviews-*.gz"))
    tasks = []
    for f in files:
        ts = ts_hour_from_filename(f.name)
        tasks.append((str(f), str(Path(a.titles_root) / ts[:10] / f"{ts[11:13]}.txt")))
    t0 = time.perf_counter()
    with ProcessPoolExecutor(a.procs) as pool:
        rows = sum(pool.map(one, tasks, chunksize=1))
    print(f"single_server procs={a.procs} files={len(files)} rows={rows} "
          f"process_seconds={time.perf_counter() - t0:.1f}", flush=True)


if __name__ == "__main__":
    main()
