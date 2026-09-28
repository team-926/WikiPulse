"""`other/pageviews` 시간별 덤프를 **HDFS 에서 읽어 Spark 로** 후보 제목만 거른다 (WP-233).

    spark-submit --py-files dp.zip batch/pageview_hourly_spark.py \\
        --input  hdfs:///wikipulse/raw/pageviews_hourly \\
        --titles hdfs:///wikipulse/replay/candidate-titles/enwiki \\
        --since 2026-06-19T00 --until 2026-08-31T23 \\
        --out    hdfs:///wikipulse/spark/pageviews_filtered

`batch.pageview_hourly_ingest.ingest_hour(titles=...)` 의 Spark 판이다. 결과
`(wiki, title, ts_hour, views, mobile_views)` 가 같아야 한다 — replay 산출물
(`filtered-v2`)과 행 단위로 대조해 교체한다.

왜 Spark 인가
    replay 필터는 한 서버에서 `ProcessPoolExecutor` 가 로컬 파일을 `zcat | grep` 으로
    읽었다. 원본이 HDFS 두 DataNode 에 블록으로 복제돼 있으면, 두 Worker 가 **자기
    디스크의 블록을 읽어**(데이터 지역성) 나눠 처리할 수 있다. 저장만 분산하고 처리를
    한 서버에서 하면 HDFS 를 쓰는 의미가 없다.

처리 순서 — 파이썬으로 넘기는 행을 JVM 에서 먼저 줄인다
    1. JVM: `en`·`en.m` 줄만 남긴다 (replay 의 `grep -E '^en(\\.m)? '` 와 같다)
    2. JVM: 제목을 canonical 로 바꿔 후보 `(ts_hour, title)` 과 semi-join.
       시간당 enwiki 약 190만 행 → 후보 수천 행
    3. 파이썬: 살아남은 **원본 줄**에 `pageview_hourly.parse_row` 를 그대로 적용한다.
       ns0 판정·canonical 규칙은 파이썬 함수가 정본이다. JVM canonical 은 후보를
       줄이는 용도일 뿐이고, 둘이 다르면 3단계에서 버려진다(대조에서 드러난다)
    4. `(ts_hour, title)` 별 합산 — 데스크톱과 모바일 행을 합치고 모바일 몫을 따로 남긴다

🔴 시각은 **파일명에서만** 온다(윈도우 끝 → 한 시간 뺀 값이 ts_hour). 경로와 시각을
   잘못 짝지으면 조회수가 통째로 밀리고 에러가 안 난다 — `ts_hour_from_filename` 과
   같은 식을 JVM 에서 쓰고, 파이썬에서 한 번 더 확인한다.

⚠️ gzip 은 분할이 안 된다 — 파일 하나가 한 파티션 이상으로 쪼개지지 않는다. Spark 가
   작은 파일 여러 개를 한 파티션에 묶을 수는 있어서, 파티션 안에서 파일(=시간)을
   섞지 않도록 합산은 `(ts_hour, title)` 키로 Spark 가 한다.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql import types as T

from batch.pageview import SchemaMismatch
from batch.pageview_hourly import (
    HOURLY_COLUMNS,
    filename_hour,
    parse_row,
    projects_for,
    ts_hour_from_filename,
)

#: 결과 스키마. `PageviewHourly` 의 필드 순서와 같다.
OUTPUT_SCHEMA = T.StructType([
    T.StructField("wiki", T.StringType(), False),
    T.StructField("title", T.StringType(), False),
    T.StructField("ts_hour", T.StringType(), False),
    T.StructField("views", T.LongType(), False),
    T.StructField("mobile_views", T.LongType(), False),
])


def hour_paths(root: str, since: str, until: str) -> list[str]:
    """`[since, until]` 의 ts_hour(윈도우 시작) → 그 시간을 담은 파일 경로.

    파일명은 윈도우 **끝**이라 `filename_hour` 로 한 시간 뒤 이름을 만든다.
    """
    start = datetime.strptime(since[:13], "%Y-%m-%dT%H")
    end = datetime.strptime(until[:13], "%Y-%m-%dT%H")
    paths = []
    while start <= end:
        date, hour = filename_hour(start.strftime("%Y-%m-%dT%H:00:00"))
        paths.append(f"{root.rstrip('/')}/pageviews-{date}-{hour}0000.gz")
        start += timedelta(hours=1)
    return paths


def ts_hour_col(path_col):
    """`.../pageviews-20260918-040000.gz` → `2026-09-18T03:00:00` (JVM 판 `ts_hour_from_filename`)."""
    stamp = F.regexp_extract(path_col, r"pageviews-(\d{8})-(\d{2})0000", 0)
    end = F.to_timestamp(F.regexp_extract(stamp, r"(\d{8}-\d{2})", 1), "yyyyMMdd-HH")
    return F.date_format(end - F.expr("INTERVAL 1 HOUR"), "yyyy-MM-dd'T'HH:00:00")


def jvm_canonical(title_col):
    """`producer.normalize.canonical_title` 의 JVM 판 — **후보를 줄이는 용도만**.

    밑줄·공백 연속 → 공백 하나, 앞뒤 공백 제거. 덤프 제목에는 공백이 없다(공백 4컬럼).
    최종 canonical 은 파이썬 `parse_row` 가 다시 낸다.
    """
    collapsed = F.regexp_replace(title_col, "[ _]+", " ")
    return F.regexp_replace(collapsed, "^ | $", "")


def candidates_frame(spark: SparkSession, titles_root: str) -> DataFrame:
    """`<root>/<YYYY-MM-DD>/<HH>.txt` (HH = 윈도우 시작) → (ts_hour, title).

    replay 필터(`refilter-fast.py`)가 읽던 후보 파일 배치 그대로다.
    """
    raw = spark.read.text(f"{titles_root.rstrip('/')}/*/*.txt").withColumn(
        "path", F.input_file_name())
    parts = F.regexp_extract("path", r"/(\d{4}-\d{2}-\d{2})/(\d{2})\.txt$", 0)
    ts = F.concat(F.regexp_extract(parts, r"(\d{4}-\d{2}-\d{2})", 1), F.lit("T"),
                  F.regexp_extract(parts, r"/(\d{2})\.txt$", 1), F.lit(":00:00"))
    return (raw.select(ts.alias("ts_hour"), F.trim("value").alias("title"))
            .where(F.col("title") != "")
            .distinct())


def _parse_partition(wiki: str):
    projects = projects_for(wiki)

    def run(rows):
        for path, ts_hour, line in rows:
            # 🔴 JVM 이 낸 ts_hour 를 파이썬 정본 함수로 다시 확인한다.
            if ts_hour_from_filename(path.rsplit("/", 1)[-1]) != ts_hour:
                raise SchemaMismatch(f"JVM ts_hour({ts_hour}) != 파일명 시각({path})")
            parsed = parse_row(line, projects)
            if parsed is None:
                continue
            title, views, is_mobile = parsed
            yield ts_hour, title, views, views if is_mobile else 0
    return run


def filter_hours(spark: SparkSession, paths: list[str], candidates: DataFrame,
                 wiki: str = "enwiki") -> DataFrame:
    """시간별 덤프 경로 → 후보만 남긴 (wiki, title, ts_hour, views, mobile_views)."""
    projects = sorted(projects_for(wiki))
    lines = (spark.read.text(paths)
             .withColumn("path", F.input_file_name())
             .withColumn("ts_hour", ts_hour_col(F.col("path"))))
    # 1) enwiki 줄만. replay 의 grep 과 같은 조건이다.
    head = F.substring_index("value", " ", 1)
    ours = lines.where(head.isin(projects))
    # 형식이 바뀌면 조용히 다른 값을 읽는다 — 파이썬 parse_row 는 여기서 예외를 던진다.
    fields = F.split("value", " ")
    ours = ours.withColumn("_ncol", F.size(fields)).withColumn(
        "_canon", jvm_canonical(fields.getItem(1)))
    # 2) 후보와 semi-join. 형식이 틀린 줄은 조인 전에 남겨 파이썬에서 예외가 나게 한다.
    bad = ours.where(F.col("_ncol") != HOURLY_COLUMNS)
    good = ours.where(F.col("_ncol") == HOURLY_COLUMNS).join(
        candidates.withColumnRenamed("title", "_canon"), ["ts_hour", "_canon"], "left_semi")
    survivors = good.unionByName(bad).select("path", "ts_hour", "value")
    # 3) 파이썬 정본 규칙으로 다시 판정.
    parsed = survivors.rdd.map(tuple).mapPartitions(_parse_partition(wiki))
    rows = spark.createDataFrame(parsed, "ts_hour string, title string, views long, "
                                         "mobile long")
    # 4) 합산. 데스크톱·모바일 두 행이 한 문서다.
    return (rows.groupBy("ts_hour", "title")
            .agg(F.sum("views").alias("views"), F.sum("mobile").alias("mobile_views"))
            .select(F.lit(wiki).alias("wiki"), "title", "ts_hour", "views", "mobile_views"))


def compare(spark: SparkSession, out: DataFrame, ref_root: str,
            since: str, until: str) -> dict[str, int]:
    """기존 산출물(JSONL.gz shard, `ingest_hour` 출력)과 행 단위 대조.

    키 `(ts_hour, title)` 로 full outer join 해 한쪽에만 있는 행과 값이 다른 행을 센다.
    셋 다 0 이어야 교체한다.
    """
    lo = f"{since[:13]}:00:00"
    hi = f"{until[:13]}:00:00"
    ref = (spark.read.json(f"{ref_root.rstrip('/')}/*/*/*/*.jsonl.gz")
           .where((F.col("ts_hour") >= lo) & (F.col("ts_hour") <= hi))
           .select("ts_hour", "title", F.col("views").cast("long").alias("ref_views"),
                   F.col("mobile_views").cast("long").alias("ref_mobile")))
    new = out.where((F.col("ts_hour") >= lo) & (F.col("ts_hour") <= hi)).select(
        "ts_hour", "title", "views", "mobile_views")
    joined = new.join(ref, ["ts_hour", "title"], "full_outer")
    row = joined.agg(
        F.count("*").alias("keys"),
        F.sum(F.col("ref_views").isNull().cast("int")).alias("only_new"),
        F.sum(F.col("views").isNull().cast("int")).alias("only_ref"),
        F.sum(((F.col("views") != F.col("ref_views"))
               | (F.col("mobile_views") != F.col("ref_mobile"))).cast("int")).alias("diff"),
    ).first()
    return {k: int(row[k] or 0) for k in ("keys", "only_new", "only_ref", "diff")}


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--input", required=True, help="시간별 덤프 디렉터리 (hdfs://...)")
    p.add_argument("--titles", required=True, help="후보 제목 루트 <date>/<HH>.txt")
    p.add_argument("--since", required=True, help="첫 ts_hour, YYYY-MM-DDTHH")
    p.add_argument("--until", required=True, help="마지막 ts_hour(포함), YYYY-MM-DDTHH")
    p.add_argument("--out", required=True, help="parquet 출력 (hdfs://...)")
    p.add_argument("--wiki", default="enwiki")
    p.add_argument("--compare-ref", default=None,
                   help="기존 JSONL.gz 산출물 루트(<wiki>/<date>/<HH>/). 주면 행 단위 대조")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    spark = (SparkSession.builder.appName("wikipulse-pageview-hourly-filter")
             .config("spark.sql.session.timeZone", "UTC")
             .getOrCreate())
    spark.sparkContext.setLogLevel("WARN")
    paths = hour_paths(args.input, args.since, args.until)
    out = filter_hours(spark, paths, candidates_frame(spark, args.titles), args.wiki)
    out.write.mode("overwrite").parquet(args.out)
    written = spark.read.parquet(args.out)
    stats = written.agg(F.count("*").alias("rows"),
                        F.countDistinct("ts_hour").alias("hours"),
                        F.sum("views").alias("views")).first()
    print(f"hours_requested={len(paths)} hours_written={stats['hours']} "
          f"rows={stats['rows']} views={stats['views']}")
    status = 0
    if args.compare_ref:
        result = compare(spark, written, args.compare_ref, args.since, args.until)
        print("compare " + " ".join(f"{k}={v}" for k, v in result.items()))
        status = 0 if result["only_new"] == result["only_ref"] == result["diff"] == 0 else 1
    spark.stop()
    return status


if __name__ == "__main__":
    raise SystemExit(main())
