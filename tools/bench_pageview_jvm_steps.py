"""-233 Spark 필터의 JVM 단계를 한 조각씩 더해 가며 잰다 (WP-235).

`bench_pageview_one_file.py` 에서 JVM 단계(G)가 25초, 읽기+en 필터(E)가 2.7초였다.
그 사이 22초가 어디서 나가는지 가른다. 파일 1개, 각 단계 2회 중 두 번째 값.

    S1  읽기 + en 필터                          (= E)
    S2  S1 + split·size·canonical 정규식
    S3  S2 + ts_hour (input_file_name → 정규식 2번 + 날짜 변환, 줄마다)
    S4  S3 + 후보 broadcast semi-join
    S5  S4 + bad 분기 union (파일을 한 번 더 읽는다)   (= 현재 survivor_lines)
    S3' S2 + ts_hour 를 파일→시각 표에서 조회(정규식 없음)
"""

from __future__ import annotations

import argparse
import time

from pyspark.sql import SparkSession
from pyspark.sql import functions as F


def timed(label, fn, repeat=2):
    took = []
    result = None
    for _ in range(repeat):
        t0 = time.perf_counter()
        result = fn()
        took.append(time.perf_counter() - t0)
    print(f"{label:<52} {took[-1]:>7.2f}s  (1회차 {took[0]:.2f}s)  → {result}", flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--hdfs-file", required=True)
    p.add_argument("--titles-root", required=True)
    a = p.parse_args()

    from batch.pageview_hourly import ts_hour_from_filename
    from batch.pageview_hourly_spark import candidates_frame, jvm_canonical, ts_hour_col

    spark = (SparkSession.builder.appName("bench-pageview-jvm-steps")
             .config("spark.sql.session.timeZone", "UTC").getOrCreate())
    spark.sparkContext.setLogLevel("WARN")
    ts = ts_hour_from_filename(a.hdfs_file.rsplit("/", 1)[-1])
    cands = (candidates_frame(spark, a.titles_root).where(F.col("ts_hour") == ts)
             .withColumnRenamed("title", "_canon").cache())
    cands.count()

    head = F.substring_index("value", " ", 1)
    s1 = spark.read.text(a.hdfs_file).where(head.isin("en", "en.m"))
    fields = F.split("value", " ")
    s2 = s1.withColumn("_ncol", F.size(fields)).withColumn(
        "_canon", jvm_canonical(fields.getItem(1)))
    s3 = s2.withColumn("path", F.input_file_name()).withColumn(
        "ts_hour", ts_hour_col(F.col("path")))
    s4 = s3.where(F.col("_ncol") == 4).join(F.broadcast(cands), ["ts_hour", "_canon"],
                                            "left_semi")
    s5 = s4.select("path", "ts_hour", "value").unionByName(
        s3.where(F.col("_ncol") != 4).select("path", "ts_hour", "value"))
    lookup = F.create_map(F.lit(a.hdfs_file), F.lit(ts))
    s3b = s2.withColumn("path", F.input_file_name()).withColumn(
        "ts_hour", F.element_at(lookup, F.col("path")))
    s4b = s3b.where(F.col("_ncol") == 4).join(F.broadcast(cands), ["ts_hour", "_canon"],
                                              "left_semi")

    timed("S1 read + en filter", s1.count)
    timed("S2 + split/size/canonical", lambda: s2.where(F.col("_ncol") == 4).count())
    timed("S3 + ts_hour regex per row", lambda: s3.where(F.col("ts_hour").isNotNull()).count())
    timed("S4 + broadcast semi-join", s4.count)
    timed("S5 + bad-branch union (second scan)", s5.count)
    timed("S3' + ts_hour from path->ts map", lambda: s3b.where(F.col("ts_hour").isNotNull()).count())
    timed("S4' map ts_hour + semi-join", s4b.count)
    spark.stop()


if __name__ == "__main__":
    main()
