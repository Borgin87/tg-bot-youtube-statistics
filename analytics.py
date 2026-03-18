import pandas as pd


def _prepare_df(snapshots: list[dict]) -> pd.DataFrame:
    if not snapshots:
        return pd.DataFrame()

    df = pd.DataFrame(snapshots).copy()
    df["ts"] = pd.to_datetime(df["ts"], utc=True, errors="coerce")
    df = df.dropna(subset=["ts"]).sort_values("ts").reset_index(drop=True)

    # числовые поля
    for col in ["subscribers", "views", "videos"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    return df


def _snapshot_before_or_equal(df: pd.DataFrame, target_ts: pd.Timestamp):
    subset = df[df["ts"] <= target_ts]
    if subset.empty:
        return None
    return subset.iloc[-1]


def _growth_for_period(df: pd.DataFrame, metric: str, days: int) -> dict | None:
    if df.empty:
        return None

    latest = df.iloc[-1]
    latest_ts = latest["ts"]
    target_ts = latest_ts - pd.Timedelta(days=days)

    base = _snapshot_before_or_equal(df, target_ts)
    if base is None:
        return None

    latest_value = int(latest[metric])
    base_value = int(base[metric])

    growth_abs = latest_value - base_value
    avg_daily = growth_abs / days if days > 0 else 0

    pct_growth = None
    if base_value > 0:
        pct_growth = (growth_abs / base_value) * 100

    return {
        "latest_value": latest_value,
        "base_value": base_value,
        "growth_abs": growth_abs,
        "avg_daily": avg_daily,
        "pct_growth": pct_growth,
        "latest_ts": latest_ts,
        "base_ts": base["ts"],
    }


def _window_growth(df: pd.DataFrame, metric: str, start_days_ago: int, end_days_ago: int) -> dict | None:
    """
    Считает рост в окне:
      start_days_ago -> end_days_ago
    Например:
      7 -> 0  = последние 7 дней
      14 -> 7 = предыдущие 7 дней
    """
    if df.empty:
        return None

    latest_ts = df.iloc[-1]["ts"]

    start_ts = latest_ts - pd.Timedelta(days=start_days_ago)
    end_ts = latest_ts - pd.Timedelta(days=end_days_ago)

    start_row = _snapshot_before_or_equal(df, start_ts)
    end_row = _snapshot_before_or_equal(df, end_ts)

    if start_row is None or end_row is None:
        return None

    start_value = int(start_row[metric])
    end_value = int(end_row[metric])

    growth_abs = end_value - start_value
    window_days = start_days_ago - end_days_ago
    avg_daily = growth_abs / window_days if window_days > 0 else 0

    pct_growth = None
    if start_value > 0:
        pct_growth = (growth_abs / start_value) * 100

    return {
        "start_value": start_value,
        "end_value": end_value,
        "growth_abs": growth_abs,
        "avg_daily": avg_daily,
        "pct_growth": pct_growth,
    }


def build_growth_report(snapshots: list[dict]) -> dict:
    df = _prepare_df(snapshots)

    if df.empty:
        return {
            "ok": False,
            "reason": "Нет данных по снапшотам."
        }

    latest = df.iloc[-1]

    periods = {}
    for days in [1, 7, 30]:
        periods[days] = {
            "subscribers": _growth_for_period(df, "subscribers", days),
            "views": _growth_for_period(df, "views", days),
            "videos": _growth_for_period(df, "videos", days),
        }

    # ускорение / замедление по подписчикам
    current_7_subs = _window_growth(df, "subscribers", 7, 0)
    previous_7_subs = _window_growth(df, "subscribers", 14, 7)

    acceleration = None
    if current_7_subs and previous_7_subs:
        current_avg = current_7_subs["avg_daily"]
        previous_avg = previous_7_subs["avg_daily"]

        diff = current_avg - previous_avg

        if diff > 0:
            trend = "ускорение"
        elif diff < 0:
            trend = "замедление"
        else:
            trend = "без изменений"

        acceleration = {
            "trend": trend,
            "current_7d_avg_daily_subs": current_avg,
            "previous_7d_avg_daily_subs": previous_avg,
            "diff_avg_daily_subs": diff,
            "current_7d_pct": current_7_subs["pct_growth"],
            "previous_7d_pct": previous_7_subs["pct_growth"],
        }

    return {
        "ok": True,
        "latest": {
            "ts": latest["ts"],
            "subscribers": int(latest["subscribers"]),
            "views": int(latest["views"]),
            "videos": int(latest["videos"]),
        },
        "periods": periods,
        "acceleration": acceleration,
        "history_points": len(df),
    }