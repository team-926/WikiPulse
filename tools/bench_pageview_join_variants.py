"""후보 조인 방식별 비용 — 파일 1개 (WP-235).

ts_hour 를 파일→시각 표로 바꾼 뒤에도 JVM 단계 8.4초 중 조인이 약 6초였다. 같은 입력에서
조인 방식만 바꿔 잰다. 각 2회 중 두 번째 값.

    J0  조인 없음 (표 조회 ts_hour + canonical 까지)
    J1  broadcast left join, 키 2개 (ts_hour, _canon)          ← 현재
    J2  broadcast left join, 키 1개 (ts_hour + TAB + _canon)
    J3  조인 없이 키 1개를 isin (InSet 해시 집합)
    J4  broadcast semi join, 키 2개
"""

from __future__ import annotations

import argparse
import time

from pyspark.sql import SparkSession
from pyspark.sql import functions as F


def timed(label, fn, repeat=2):
    took, result = [], None
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
    from batch.pageview_hourly_spark import candidates_frame, jvm_canonical

    spark = (SparkSession.builder.appName("bench-pageview-join-variants")
             .config("spark.sql.session.timeZone", "UTC").getOrCreate())
    spark.sparkContext.setLogLevel("WARN")
    name = a.hdfs_file.rsplit("/", 1)[-1]
    ts = ts_hour_from_filename(name)
    cands = (candidates_frame(spark, a.titles_root).where(F.col("ts_hour") == ts)
             .withColumnRenamed("title", "_canon")
             .withColumn("_key", F.concat_ws("\t", "ts_hour", "_canon"))
             .withColumn("_hit", F.lit(True)).cache())
    keys = [r["_key"] for r in cands.select("_key").collect()]
    print(f"candidates={len(keys)}", flush=True)

    ts_map = F.create_map(F.lit(name), F.lit(ts))
    fields = F.split("value", " ")
    base = (spark.read.text(a.hdfs_file)
            .where(F.substring_index("value", " ", 1).isin("en", "en.m"))
            .withColumn("ts_hour", F.element_at(
                ts_map, F.substring_index(F.input_file_name(), "/", -1)))
            .withColumn("_ncol", F.size(fields))
            .withColumn("_canon", jvm_canonical(fields.getItem(1)))
            .withColumn("_key", F.concat_ws("\t", "ts_hour", "_canon")))
    keep = F.col("_hit") | (F.col("_ncol") != 4)

    timed("J0 no join", lambda: base.where(F.col("_canon").isNotNull()).count())
    timed("J1 broadcast left join, 2 keys (current)", lambda: base.join(
        F.broadcast(cands.select("ts_hour", "_canon", "_hit")), ["ts_hour", "_canon"],
        "left").where(keep).count())
    timed("J2 broadcast left join, 1 concat key", lambda: base.join(
        F.broadcast(cands.select("_key", "_hit")), ["_key"], "left").where(keep).count())
    timed("J3 isin on 1 concat key (InSet)", lambda: base.where(
        F.col("_key").isin(keys) | (F.col("_ncol") != 4)).count())
    timed("J4 broadcast semi join, 2 keys", lambda: base.join(
        F.broadcast(cands.select("ts_hour", "_canon")), ["ts_hour", "_canon"],
        "left_semi").count())

    # J5: 줄마다 정규식을 안 쓴다. 제목은 substring_index 두 번, canonical 은 translate.
    #     translate 가 정본 canonical 과 다를 수 있는 줄(__·앞뒤 _)은 파이썬으로 보낸다.
    raw_title = F.substring_index(F.substring_index("value", " ", 2), " ", -1)
    n_space = F.length("value") - F.length(F.translate("value", " ", ""))
    cheap = (spark.read.text(a.hdfs_file)
             .where(F.substring_index("value", " ", 1).isin("en", "en.m"))
             .withColumn("ts_hour", F.element_at(
                 ts_map, F.substring_index(F.input_file_name(), "/", -1)))
             .withColumn("_raw", raw_title)
             .withColumn("_canon", F.translate("_raw", "_", " ")))
    odd = (F.col("_raw").contains("__") | F.col("_raw").startswith("_")
           | F.col("_raw").endswith("_") | (n_space != 3))
    timed("J0' no join, cheap title/canonical", lambda: cheap.where(
        F.col("_canon").isNotNull()).count())
    timed("J5 cheap + broadcast left join, 2 keys", lambda: cheap.join(
        F.broadcast(cands.select("ts_hour", "_canon", "_hit")), ["ts_hour", "_canon"],
        "left").where(F.col("_hit") | odd).count())
    spark.stop()


if __name__ == "__main__":
    main()
