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
import time
from datetime import datetime, timedelta

from pyspark import StorageLevel
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
    survivors = survivor_lines(spark, paths, candidates, wiki)
    # 3) 파이썬 정본 규칙으로 다시 판정.
    parsed = survivors.rdd.map(tuple).mapPartitions(_parse_partition(wiki))
    rows = spark.createDataFrame(parsed, "ts_hour string, title string, views long, "
                                         "mobile long")
    # 4) 합산. 데스크톱·모바일 두 행이 한 문서다.
    return (rows.groupBy("ts_hour", "title")
            .agg(F.sum("views").alias("views"), F.sum("mobile").alias("mobile_views"))
            .select(F.lit(wiki).alias("wiki"), "title", "ts_hour", "views", "mobile_views"))


#: 태스크 안 전처리 — replay 필터(`refilter-fast.py`)의 앞단과 같은 조건.
GREP_EN = "zcat | LC_ALL=C grep -E '^en(\\.m)? '"


def filter_hours_grep(spark: SparkSession, paths: list[str],
                      titles_by_hour: dict[str, frozenset[str]],
                      wiki: str = "enwiki") -> DataFrame:
    """`--mode grep` — 태스크가 HDFS 파일을 통째로 받아 `zcat | grep` 뒤 파이썬 합산.

    벤치(WP-235, 파일 1개 47.7 MB)에서 JVM 경로는 개선 뒤에도 파일당 8~9초가
    바닥이었고(split·canonical 정규식이 en 줄 206만 개마다), `zcat | grep | aggregate` 는
    6.0초였다. 그 가장 싼 경로를 **HDFS 블록이 있는 서버의 태스크 안에서** 돌린다.

    * `binaryFiles` 는 파일 단위 입력이라 블록 위치(preferred location)를 그대로 쓴다.
      gz 는 어차피 분할이 안 되고 파일 하나가 블록 하나(평균 56 MB)다
    * 합산은 `pageview_hourly.aggregate(titles=…)` 그대로 — `ingest_hour` 와 같은 규칙,
      형식이 틀린 en 줄은 `parse_row` 가 예외를 던진다
    * 후보는 시간별 frozenset 을 broadcast 한다(하루 약 7만 제목)
    """
    sc = spark.sparkContext
    titles_bc = sc.broadcast(titles_by_hour)

    def run(items):
        import subprocess
        import threading

        from batch.pageview_hourly import aggregate

        for path, data in items:
            ts = ts_hour_from_filename(path.rsplit("/", 1)[-1])
            titles = titles_bc.value.get(ts)
            if not titles:
                continue                      # 그 시간 후보 파일이 없다 — replay 의 no_titles
            proc = subprocess.Popen(GREP_EN, shell=True, stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE)
            feeder = threading.Thread(target=_feed, args=(proc.stdin, data), daemon=True)
            feeder.start()
            lines = (raw.decode("utf-8", errors="replace") for raw in proc.stdout)
            rows = list(aggregate(lines, wiki, ts, titles=titles))
            feeder.join()
            code = proc.wait()
            if code not in (0, 1):            # grep 1 = 일치 없음. 그 밖은 실패다
                raise RuntimeError(f"{GREP_EN} 실패 (exit {code}): {path}")
            for rec in rows:
                yield rec.wiki, rec.title, rec.ts_hour, rec.views, rec.mobile_views

    rdd = sc.binaryFiles(",".join(paths), minPartitions=len(paths)).mapPartitions(run)
    return spark.createDataFrame(rdd, OUTPUT_SCHEMA)


def _feed(pipe, data: bytes) -> None:
    try:
        pipe.write(data)
    finally:
        pipe.close()


def titles_by_hour(candidates: DataFrame, hours: list[str]) -> dict[str, frozenset[str]]:
    """후보 DataFrame → {ts_hour: frozenset(title)}. 드라이버로 모은다(며칠치는 수십만 행)."""
    grouped: dict[str, set[str]] = {}
    for row in candidates.where(F.col("ts_hour").isin(hours)).toLocalIterator():
        grouped.setdefault(row["ts_hour"], set()).add(row["title"])
    return {ts: frozenset(titles) for ts, titles in grouped.items()}


def survivor_lines(spark: SparkSession, paths: list[str], candidates: DataFrame,
                   wiki: str = "enwiki") -> DataFrame:
    """JVM 단계만 — 후보에 걸린 원본 줄 `(path, ts_hour, value)`.

    파이썬으로 넘어가기 전 경계다. 따로 둔 이유: 파이썬 RDD 경계에서 실행 계획이 끊겨
    `filter_hours(...).explain()` 에는 이 앞단이 안 보인다 — 벤치(WP-235)가 이걸
    따로 세고 explain 한다.
    """
    projects = sorted(projects_for(wiki))
    # 1) enwiki 줄만. replay 의 grep 과 같은 조건이다. **시각보다 먼저** 거른다.
    head = F.substring_index("value", " ", 1)
    ours = spark.read.text(paths).where(head.isin(projects))
    # 시각은 **파일마다 한 번** — 드라이버가 파일 목록을 알고 있으니 파일명→ts_hour 표를
    # 만들어 조회한다. ~~줄마다 input_file_name 에 정규식 2번 + 날짜 변환~~ 은 en 줄
    # 206만 개마다 돌아 파일 1개에 +4.9초였고, 그 문자열 키 때문에 조인도 느렸다
    # (벤치 WP-235: 표 조회로 바꾸자 JVM 단계 17.0s → 7.9s).
    # 키는 경로가 아니라 **파일명**이다 — `hdfs:///…` 와 `hdfs://host:8020/…` 처럼 같은
    # 파일을 다르게 적으면 경로 키는 조용히 null 이 된다.
    names = {p.rsplit("/", 1)[-1]: ts_hour_from_filename(p.rsplit("/", 1)[-1])
             for p in paths}
    ts_map = F.create_map(*[F.lit(x) for kv in sorted(names.items()) for x in kv])
    fields = F.split("value", " ")
    ours = (ours.withColumn("path", F.input_file_name())
            .withColumn("ts_hour", F.element_at(ts_map, F.substring_index("path", "/", -1)))
            .withColumn("_ncol", F.size(fields))
            .withColumn("_canon", jvm_canonical(fields.getItem(1))))
    # 2) 후보와 broadcast 조인 — **한 번만 읽는다**. 형식이 틀린 줄(_ncol != 4)은 후보와
    #    상관없이 남겨 파이썬 parse_row 가 예외를 던지게 한다. ~~semi-join + bad 분기 union~~
    #    은 파일을 두 번 읽었다(+1.2초).
    #    🔴 후보를 **broadcast** 한다. 안 하면 sort-merge join 이 큰 쪽(enwiki 전체 줄,
    #    시간당 약 190만 행)을 셔플한다 — 1,776시간 한 번에 돌렸을 때 셔플 임시 파일이
    #    데이터 EC2 디스크를 채워 `No space left on device` 로 죽었고 NameNode 가 안전
    #    모드에 들어갔다 (2026-09-28). 그래서 호출하는 쪽(main)이 며칠씩 나눠 후보를 작게
    #    유지한다(하루 약 7만 행).
    hit = (candidates.withColumnRenamed("title", "_canon")
           .withColumn("_hit", F.lit(True)))
    joined = ours.join(F.broadcast(hit), ["ts_hour", "_canon"], "left")
    return (joined.where(F.col("_hit") | (F.col("_ncol") != HOURLY_COLUMNS))
            .select("path", "ts_hour", "value"))


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
    p.add_argument("--mode", choices=("jvm", "grep"), default="jvm",
                   help="jvm = DataFrame 필터·조인 / grep = 태스크 안 zcat|grep + aggregate")
    p.add_argument("--days-per-batch", type=int, default=1,
                   help="한 번에 묶어 처리할 날 수 (후보 broadcast 크기와 코어 꼬리의 절충)")
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
    # 작은 파일 1,776개라 하루마다 다시 읽으면 목록 조회만 수십 번이다 — 한 번 읽어 둔다.
    candidates = candidates_frame(spark, args.titles).persist(StorageLevel.MEMORY_AND_DISK)
    # 며칠씩 묶는다 — 후보 broadcast 를 작게 유지하면서(filter_hours 의 🔴) 묶음 끝마다
    # 코어가 노는 꼬리와 쓰기 작업 기동 비용을 줄인다. ~~하루씩(74번)~~ 은 24파일이 4코어에
    # 여러 번 나뉘어 돌며 매일 마지막 묶음에서 코어가 놀았다 (WP-235).
    days = sorted({p.rsplit("pageviews-", 1)[1][:8] for p in paths})
    step = max(1, args.days_per_batch)
    first = True
    loop_started = time.perf_counter()
    for i in range(0, len(days), step):
        batch_started = time.perf_counter()
        batch_days = set(days[i:i + step])
        batch_paths = [p for p in paths if p.rsplit("pageviews-", 1)[1][:8] in batch_days]
        # 파일명 날짜는 윈도우 끝이라 00시 파일은 전날 23시다 — 후보는 경로의 ts_hour 로 거른다.
        hours = [ts_hour_from_filename(p.rsplit("/", 1)[-1]) for p in batch_paths]
        if args.mode == "grep":
            out = filter_hours_grep(spark, batch_paths, titles_by_hour(candidates, hours),
                                    args.wiki)
        else:
            batch_cands = candidates.where(F.col("ts_hour").isin(hours))
            out = filter_hours(spark, batch_paths, batch_cands, args.wiki)
        out.write.mode("overwrite" if first else "append").parquet(args.out)
        first = False
        print(f"batch {min(batch_days)}~{max(batch_days)} files={len(batch_paths)} "
              f"{time.perf_counter() - batch_started:.1f}s", flush=True)
    # 처리 구간만 — Spark 기동·후보 읽기·대조는 뺀다. 벤치(WP-235)가 이 값을 쓴다.
    print(f"process_seconds={time.perf_counter() - loop_started:.1f} files={len(paths)} "
          f"mode={args.mode}", flush=True)
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
