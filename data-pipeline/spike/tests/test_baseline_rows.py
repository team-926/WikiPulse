"""기준선 행 산출·적재 검증 (WP-60). Spark·DB 없이 돈다."""

from __future__ import annotations

from datetime import date

import pytest

from spike.baseline_rows import BASELINE_WINDOW_DAYS, build_rows
from spike.baseline_sink import (
    INSERT_MISSING_PAGES_SQL,
    SELECT_PAGE_IDS_SQL,
    UPSERT_BASELINE_SQL,
    resolve_page_ids,
    upsert_rows,
)
from spike.detector import MIN_BASELINE_SAMPLE_DAYS, Baseline, Window, detect


def win(day, hour_of_day, edits, views=None, wiki="enwiki", title="Iran"):
    """-58 산출물 한 행. window_start 의 시각을 hour_of_day 와 맞춰 둔다."""
    return {"wiki": wiki, "title": title, "hour_of_day": hour_of_day,
            "window_start": f"{day}T{hour_of_day % 24:02d}:00:00",
            "edit_count": edits, "views": views}


# ---------------------------------------------------------------- EWMA 산출

def test_최근_관측이_더_무겁다():
    # 같은 슬롯, 2025-06-09(최근) 10편집 / 2025-05-26(14일 전) 0편집
    rows = build_rows([win("2025-06-09", 0, 10), win("2025-05-26", 0, 0)],
                      as_of=date(2025, 6, 9), halflife_days=14.0)
    assert len(rows) == 1
    # 가중 (10*1 + 0*0.5) / 1.5 = 6.667 — 단순평균 5 보다 크다
    assert rows[0].edit_ewma == pytest.approx(6.6667, abs=1e-3)


def test_조회수도_같은_가중():
    rows = build_rows([win("2025-06-09", 0, 1, views=100),
                       win("2025-05-26", 0, 1, views=0)],
                      as_of=date(2025, 6, 9), halflife_days=14.0)
    assert rows[0].view_ewma == pytest.approx(66.6667, abs=1e-3)


def test_조회수_전부_결측이면_view_ewma_None():
    rows = build_rows([win("2025-06-09", 0, 3, views=None)], as_of=date(2025, 6, 9))
    assert rows[0].view_ewma is None
    assert rows[0].edit_ewma == 3.0


# ---------------------------------------------------------------- 28일 경계

def test_창_밖_관측은_버린다():
    # as_of 기준 29일 전은 창 밖(경계는 (as_of-28, as_of])
    rows = build_rows([win("2025-06-30", 0, 10), win("2025-06-01", 0, 999)],
                      as_of=date(2025, 6, 30), halflife_days=1e9)
    assert len(rows) == 1
    assert rows[0].edit_ewma == 10.0          # 999 는 안 섞였다
    assert rows[0].sample_days == 1


def test_창_경계_정확히_28일전은_포함():
    as_of = date(2025, 6, 30)
    edge = date.fromordinal(as_of.toordinal() - (BASELINE_WINDOW_DAYS - 1))
    rows = build_rows([win(edge.isoformat(), 0, 5)], as_of=as_of, halflife_days=1e9)
    assert len(rows) == 1 and rows[0].edit_ewma == 5.0


def test_창_안에_관측이_없으면_행을_안_낸다():
    # 기준선 없음과 기준선 0 은 다른 뜻이다 — detector 가 None 을 신규 문서로 본다
    rows = build_rows([win("2025-01-01", 0, 10)], as_of=date(2025, 6, 30))
    assert rows == []


# ---------------------------------------------------------------- sample_days

def test_sample_days는_고유_날짜수():
    # 같은 날 두 행(다른 슬롯 아님, 같은 슬롯)이면 하루로 센다
    rows = build_rows([win("2025-06-09", 0, 1), win("2025-06-09", 0, 2),
                       win("2025-06-02", 0, 3)],
                      as_of=date(2025, 6, 9))
    assert rows[0].sample_days == 2


def test_얇은_baseline은_detector가_신규문서로_보낸다():
    rows = build_rows([win("2025-06-09", 0, 5)], as_of=date(2025, 6, 9))
    baseline = Baseline(rows[0].edit_ewma, rows[0].edit_stddev,
                        rows[0].view_ewma, rows[0].sample_days)
    assert rows[0].sample_days < MIN_BASELINE_SAMPLE_DAYS
    assert baseline.is_thin is True
    # 얇으면 z 를 안 쓰고 절대 편집수 경로 — 편집 3건은 미달
    assert detect(Window(edit_count=3, editor_count=1, views=None), baseline).is_spike is False


def test_두꺼운_baseline은_z경로로_간다():
    # 7일치 평상시 1편집 -> 급증 20편집이면 잡혀야 한다
    days = [f"2025-06-{d:02d}" for d in range(3, 10)]
    rows = build_rows([win(d, 0, 1) for d in days], as_of=date(2025, 6, 9),
                      halflife_days=1e9)
    row = rows[0]
    assert row.sample_days == 7 and row.edit_stddev == pytest.approx(0.0)
    baseline = Baseline(row.edit_ewma, row.edit_stddev, row.view_ewma, row.sample_days)
    assert baseline.is_thin is False
    # stddev 0 이면 z 계산 불가 -> detector 가 편집 미달로 처리(조용히 통과시키지 않는다)
    assert detect(Window(edit_count=20, editor_count=3, views=None), baseline).is_spike is False


def test_산출한_행이_detector_에_그대로_먹는다():
    """build_rows 산출물을 Baseline 으로 바로 넣었을 때 2단계 판정이 도는지.

    ~~평상시 1~3 편집 -> 40 편집이면 급증~~ → **편집은 더 이상 관문이 아니다**
    (2026-09-18, WP-126). 조회수가 없으면 편집이 아무리 튀어도 후보 대기다.
    여기서 보는 건 산출한 기준선이 판정 입력으로 성립하는지까지다.
    """
    counts = [1, 3, 2, 1, 3, 2, 1]
    days = [f"2025-06-{d:02d}" for d in range(3, 10)]
    rows = build_rows([win(d, 0, c, views=200) for d, c in zip(days, counts)],
                      as_of=date(2025, 6, 9), halflife_days=1e9)
    row = rows[0]
    assert row.sample_days == 7 and row.edit_stddev > 0
    assert row.view_ewma == 200                       # 조회수 기준선도 같이 산출된다

    baseline = Baseline(row.edit_ewma, row.edit_stddev, row.view_ewma,
                        row.sample_days, row.view_stddev)

    # 조회수 미도착 — 편집 z 가 임계를 훌쩍 넘어도 확정이 아니다
    pending = detect(Window(edit_count=40, editor_count=5, views=None), baseline)
    assert pending.is_pending
    assert pending.edit_z > 3.0                       # 진단값으로는 여전히 실린다

    # 조회수가 도착하고 급등하면 확정. 기준선 200 -> 5,000 (25배)
    confirmed = detect(Window(edit_count=1, editor_count=1, views=5_000), baseline)
    assert confirmed.is_spike
    assert confirmed.is_new_page is False


# ---------------------------------------------------------------- 적재 SQL

class FakeCursor:
    """psycopg 커서 흉내. 실행된 SQL·파라미터를 기록한다."""

    def __init__(self):
        self.calls: list[tuple[str, object]] = []
        self.many: list[tuple[str, list]] = []
        self._next_id = 100

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    def executemany(self, sql, seq):
        self.many.append((sql, list(seq)))

    def fetchone(self):
        self._next_id += 1
        return (self._next_id,)


class FakePageCursor(FakeCursor):
    """wiki_page 를 흉내 낸다 — SELECT 는 있는 것만, INSERT 는 없는 것만 만든다."""

    def __init__(self, existing: dict[str, int]):
        super().__init__()
        self.pages = dict(existing)
        self._rows: list[tuple[str, int]] = []

    def execute(self, sql, params=None):
        super().execute(sql, params)
        _wiki, titles = params
        if sql is SELECT_PAGE_IDS_SQL:
            self._rows = [(t, self.pages[t]) for t in titles if t in self.pages]
        elif sql is INSERT_MISSING_PAGES_SQL:
            for t in sorted(titles):
                self._next_id += 1
                self.pages.setdefault(t, self._next_id)

    def fetchall(self):
        return self._rows


def test_page_id_해석은_고유키당_한_번():
    cur = FakePageCursor({"Iran": 7})
    keys = [("enwiki", "Iran")] * 24 + [("enwiki", "Milton")]
    resolved = resolve_page_ids(cur, keys)
    # SELECT 1 · 없는 Milton 만 INSERT 1 · 넣은 것 SELECT 1 — 24번이 아니다
    assert [sql for sql, _ in cur.calls] == [
        SELECT_PAGE_IDS_SQL, INSERT_MISSING_PAGES_SQL, SELECT_PAGE_IDS_SQL]
    assert cur.calls[0][1] == ("enwiki", ["Iran", "Milton"])
    assert cur.calls[1][1] == ("enwiki", ["Milton"])
    assert resolved[("enwiki", "Iran")] == 7
    assert set(resolved) == {("enwiki", "Iran"), ("enwiki", "Milton")}


def test_이미_있는_문서만이면_INSERT_하지_않는다():
    """WP-234. 있는 문서에 쓰기(잠금)를 하지 않는 게 데드락 수정의 핵심이다."""
    cur = FakePageCursor({"Iran": 7, "Milton": 8})
    resolve_page_ids(cur, [("enwiki", "Milton"), ("enwiki", "Iran")])
    assert [sql for sql, _ in cur.calls] == [SELECT_PAGE_IDS_SQL]


def test_새_문서는_정렬된_순서로_넣는다():
    """호출자마다 입력 순서가 달라도 잠금(삽입) 순서가 같아야 교착이 안 난다."""
    cur = FakePageCursor({})
    resolve_page_ids(cur, [("enwiki", "Zeta"), ("enwiki", "Alpha"), ("enwiki", "Mid")])
    assert cur.calls[1] == (INSERT_MISSING_PAGES_SQL, ("enwiki", ["Alpha", "Mid", "Zeta"]))
    assert "ORDER BY t" in INSERT_MISSING_PAGES_SQL


def test_upsert_SQL이_기존_행을_잠그지_않는다():
    assert "DO NOTHING" in INSERT_MISSING_PAGES_SQL
    assert "DO UPDATE" not in INSERT_MISSING_PAGES_SQL
    assert "FOR UPDATE" not in SELECT_PAGE_IDS_SQL


def test_upsert는_PK충돌시_갱신():
    assert "ON CONFLICT (page_id, hour_of_day) DO UPDATE" in UPSERT_BASELINE_SQL
    assert "updated_at  = now()" in UPSERT_BASELINE_SQL

    rows = build_rows([win("2025-06-09", 0, 4, views=10)], as_of=date(2025, 6, 9))
    cur = FakeCursor()
    written = upsert_rows(cur, rows, {("enwiki", "Iran"): 7})
    assert written == 1
    sql, params = cur.many[0]
    # page_id 가 앞에 붙고, view_stddev 가 view_ewma 뒤에 온다 (WP-90).
    # 관측이 하나뿐이라 두 표준편차가 다 0.0 이다 — None(표본 없음)과 다른 뜻이다.
    assert params == [(7, 0, 4.0, 0.0, 10.0, 0.0, 1)]


def test_같은_입력을_두_번_돌려도_같은_파라미터():
    """멱등성의 산출 쪽. 실제 행 수 불변은 실 PostgreSQL 로 확인해야 한다(README)."""
    windows = [win("2025-06-09", 0, 4), win("2025-06-02", 0, 2)]
    first = build_rows(windows, as_of=date(2025, 6, 9))
    second = build_rows(windows, as_of=date(2025, 6, 9))
    assert first == second


# --- window_start 타입 (WP-212) ---

def test_window_start_는_문자열과_datetime_둘_다_받는다():
    """-58 산출물은 문자열, DB 경로(baseline_from_views)는 datetime 을 준다."""
    from datetime import datetime, timezone

    from spike.baseline_rows import _day

    assert _day("2026-09-20T14:00:00") == date(2026, 9, 20)
    assert _day(datetime(2026, 9, 20, 14, tzinfo=timezone.utc)) == date(2026, 9, 20)


def test_tz_aware_datetime_은_UTC_로_맞춘_뒤_날짜를_뗀다():
    """⚠️ KST 09:00 은 UTC 로 전날 00:00 이다. 안 맞추면 슬롯이 하루 밀린다."""
    from datetime import datetime, timedelta, timezone

    from spike.baseline_rows import _day

    kst = timezone(timedelta(hours=9))
    assert _day(datetime(2026, 9, 21, 8, tzinfo=kst)) == date(2026, 9, 20)
