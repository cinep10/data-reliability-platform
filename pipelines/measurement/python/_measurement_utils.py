import pymysql

def connect(args):
    return pymysql.connect(
        host=args.db_host,
        port=int(args.db_port),
        user=args.db_user,
        password=args.db_pass,
        database=args.db_name,
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )

def table_exists(cur, table):
    cur.execute(
        "SELECT COUNT(*) c FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s",
        (table,),
    )
    return int(cur.fetchone()["c"]) > 0

def columns(cur, table):
    if not table_exists(cur, table):
        return set()
    cur.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s",
        (table,),
    )
    return {r["column_name"] for r in cur.fetchall()}

def first_col(cols, candidates):
    for c in candidates:
        if c in cols:
            return c
    return None

def safe_float(v, default=0.0):
    try:
        if v is None:
            return default
        return float(v)
    except Exception:
        return default

def safe_int(v, default=0):
    try:
        if v is None:
            return default
        return int(float(v))
    except Exception:
        return default

def count_rows(cur, table, profile_id, dt, run_id="", date_candidates=("dt","target_date")):
    cols = columns(cur, table)
    if not cols:
        return 0
    date_col = first_col(cols, date_candidates)
    if not date_col:
        return 0
    where = [f"{date_col}=%s"]
    params = [dt]
    if "profile_id" in cols:
        where.append("profile_id=%s")
        params.append(profile_id)
    if run_id and "run_id" in cols:
        cur.execute(f"SELECT COUNT(*) c FROM {table} WHERE {' AND '.join(where)} AND run_id=%s", tuple(params + [run_id]))
        n = safe_int(cur.fetchone()["c"])
        if n > 0:
            return n
    cur.execute(f"SELECT COUNT(*) c FROM {table} WHERE {' AND '.join(where)}", tuple(params))
    return safe_int(cur.fetchone()["c"])

def scalar(cur, sql, params=(), default=0):
    try:
        cur.execute(sql, params)
        row = cur.fetchone()
        if not row:
            return default
        return list(row.values())[0]
    except Exception:
        return default

def agg_metric(cur, table, metric_candidates, profile_id, dt, run_id="", agg="MAX", date_candidates=("dt","target_date")):
    cols = columns(cur, table)
    if not cols:
        return 0
    metric = first_col(cols, metric_candidates)
    date_col = first_col(cols, date_candidates)
    if not metric or not date_col:
        return 0
    where = [f"{date_col}=%s"]
    params = [dt]
    if "profile_id" in cols:
        where.append("profile_id=%s")
        params.append(profile_id)
    if run_id and "run_id" in cols:
        v = scalar(cur, f"SELECT COALESCE({agg}({metric}),0) v FROM {table} WHERE {' AND '.join(where)} AND run_id=%s", tuple(params + [run_id]), 0)
        if safe_float(v) != 0:
            return safe_float(v)
    return safe_float(scalar(cur, f"SELECT COALESCE({agg}({metric}),0) v FROM {table} WHERE {' AND '.join(where)}", tuple(params), 0))
