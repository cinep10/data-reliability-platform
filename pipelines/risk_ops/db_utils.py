import argparse
import os
from typing import Iterable, List, Optional, Sequence, Tuple


def get_connection(args):
    try:
        import pymysql
        return pymysql.connect(
            host=args.db_host,
            port=int(args.db_port),
            user=args.db_user,
            password=args.db_pass,
            database=args.db_name,
            charset='utf8mb4',
            autocommit=False,
            cursorclass=pymysql.cursors.Cursor,
        )
    except Exception:
        import mysql.connector
        return mysql.connector.connect(
            host=args.db_host,
            port=int(args.db_port),
            user=args.db_user,
            password=args.db_pass,
            database=args.db_name,
            charset='utf8mb4',
            autocommit=False,
        )


def add_db_args(parser: argparse.ArgumentParser):
    parser.add_argument('--db-host', default=os.getenv('DB_HOST', '127.0.0.1'))
    parser.add_argument('--db-port', default=os.getenv('DB_PORT', '3306'))
    parser.add_argument('--db-user', default=os.getenv('DB_USER', 'root'))
    parser.add_argument('--db-pass', default=os.getenv('DB_PASS', os.getenv('DB_PASSWORD', '')))
    parser.add_argument('--db-name', default=os.getenv('DB_NAME', 'weblog'))


def fetch_all(conn, sql: str, params: Optional[Sequence] = None):
    with conn.cursor() as cur:
        cur.execute(sql, params or [])
        return cur.fetchall()


def execute(conn, sql: str, params: Optional[Sequence] = None):
    with conn.cursor() as cur:
        cur.execute(sql, params or [])


def execute_many(conn, sql: str, seq_params: Iterable[Sequence]):
    with conn.cursor() as cur:
        cur.executemany(sql, list(seq_params))


def get_columns(conn, table_name: str, schema_name: str) -> List[str]:
    rows = fetch_all(
        conn,
        """
        SELECT COLUMN_NAME
        FROM information_schema.columns
        WHERE table_schema=%s AND table_name=%s
        ORDER BY ordinal_position
        """,
        [schema_name, table_name],
    )
    return [r[0] for r in rows]


def pick_column(existing: List[str], candidates: Sequence[str], required: bool = True) -> Optional[str]:
    lowered = {c.lower(): c for c in existing}
    for cand in candidates:
        if cand.lower() in lowered:
            return lowered[cand.lower()]
    if required:
        raise RuntimeError(f'Unable to find any of columns {candidates}. Existing={existing}')
    return None


def quote_ident(name: str) -> str:
    return '`' + name.replace('`', '``') + '`'
