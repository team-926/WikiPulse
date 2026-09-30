"""시간별 조회수 덤프 **파일 1개**로 필터 경로를 단계별로 잰다 (WP-235).

    spark-submit --py-files dp.zip tools/bench_pageview_one_file.py \\
        --hdfs-file hdfs://…/pageviews-20260725-040000.gz --local-file /tmp/p.gz \\
        --titles hdfs://…/candidate-titles/2026-07-25/03.txt

-233 Spark 필터는 태스크 시간의 99%가 한 스테이지(읽기→필터→조인→파이썬)였고, PySpark
입력이 별도 스레드라 이벤트 로그로는 "JVM 디코딩 vs 파이썬" 을 못 갈랐다. 그래서 같은
파일을 경로마다 따로 돌려 **어디서 시간을 쓰는지** 가른다.

    A  zcat                         압축 해제만 (하한)
    B  zcat | grep '^en(\\.m)? '     기존 replay 필터의 앞단
    C  B + 파이썬 aggregate          기존 replay 필터 전체 (ingest_hour 와 같은 규칙)
    D  Spark read.text().count()    JVM 이 모든 줄을 행으로 만드는 비용
    E  D + en 필터 count            JVM 필터까지
    F  현재 filter_hours (1시간)    -233 경로 전체
    + F 의 explain — 필터가 input_file_name() 앞으로 당겨졌는지

Spark 쪽은 파일이 하나라 태스크 하나 = 코어 하나다. A~C 도 한 프로세스라 코어당
비교가 된다. 각 단계는 2회 돌려 두 번째 값을 쓴다(캐시·JIT 워밍업 영향 줄이기).
"""

from __future__ import annotations

import argparse
import subprocess
import time

from pyspark.sql import SparkSession
from pyspark.sql import functions as F


def timed(label, fn, repeat=2):
    result = None
    took = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        result = fn()
        took.append(time.perf_counter() - t0)
    print(f"{label:<44} {took[-1]:>7.2f}s  (1회차 {took[0]:.2f}s)  → {result}", flush=True)
    return result


def shell(cmd):
    return subprocess.run(cmd, shell=True, check=True, capture_output=True,
                          text=True).stdout.strip()


def python_aggregate(local_file, titles_file):
    from batch.pageview_hourly import aggregate, ts_hour_from_filename
    titles = frozenset(line.strip() for line in open(titles_file, encoding="utf-8")
                       if line.strip())
    proc = subprocess.Popen(f"zcat '{local_file}' | LC_ALL=C grep -E '^en(\\.m)? '",
                            shell=True, stdout=subprocess.PIPE, text=True,
                            encoding="utf-8", errors="replace")
    ts = ts_hour_from_filename(local_file.rsplit("/", 1)[-1])
    rows = sum(1 for _ in aggregate(proc.stdout, "enwiki", ts, titles=titles))
    proc.wait()
    return rows


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--hdfs-file", required=True)
    p.add_argument("--local-file", required=True)
    p.add_argument("--titles", required=True, help="그 시간 후보 파일 (hdfs://)")
    p.add_argument("--local-titles", required=True, help="같은 후보 파일의 로컬 사본")
    a = p.parse_args()

    f = a.local_file
    print(f"file={f} size={int(shell(f'stat -c %s {f}')) / 1e6:.1f}MB", flush=True)
    timed("A zcat | wc -l", lambda: int(shell(f"zcat {f} | wc -l")))
    timed("B zcat | grep en | wc -l",
          lambda: int(shell(f"zcat {f} | LC_ALL=C grep -E '^en(\\.m)? ' | wc -l")))
    timed("C zcat | grep | python aggregate (rows)",
          lambda: python_aggregate(f, a.local_titles))

    spark = (SparkSession.builder.appName("bench-pageview-one-file")
             .config("spark.sql.session.timeZone", "UTC").getOrCreate())
    spark.sparkContext.setLogLevel("WARN")
    timed("D spark read.text count", lambda: spark.read.text(a.hdfs_file).count())
    timed("E spark read + en filter count", lambda: spark.read.text(a.hdfs_file).where(
        F.substring_index("value", " ", 1).isin("en", "en.m")).count())

    from batch.pageview_hourly_spark import candidates_frame, filter_hours
    day_root = a.titles.rsplit("/", 2)[0]
    all_cands = candidates_frame(spark, day_root)
    from batch.pageview_hourly import ts_hour_from_filename
    ts = ts_hour_from_filename(a.hdfs_file.rsplit("/", 1)[-1])
    one = all_cands.where(F.col("ts_hour") == ts).cache()
    one.count()
    from batch.pageview_hourly_spark import survivor_lines
    surv = survivor_lines(spark, [a.hdfs_file], one)
    timed("G JVM stage only: survivor_lines count", lambda: surv.count())
    out = filter_hours(spark, [a.hdfs_file], one)
    timed("F current filter_hours (rows)", lambda: out.count())
    print("---- explain (G: JVM stage) ----")
    surv.explain(mode="formatted")
    spark.stop()


if __name__ == "__main__":
    main()
