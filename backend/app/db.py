import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

数据目录 = Path(os.environ.get("数据目录", Path(__file__).resolve().parent.parent / "data"))
夹具目录 = Path(os.environ.get("夹具目录", Path(__file__).resolve().parent.parent.parent / "fixtures"))
库路径 = 数据目录 / "闸对.db"


def 连接() -> sqlite3.Connection:
    数据目录.mkdir(parents=True, exist_ok=True)
    # 超时扫描与出站写闸可能并发：给锁等待留时间，别让并发直接抛 database is locked。
    # isolation_level=None = 自动提交，事务由 `事务()` 显式开 BEGIN IMMEDIATE。
    c = sqlite3.connect(库路径, timeout=30, isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    c.execute("PRAGMA busy_timeout = 20000")
    try:
        c.execute("PRAGMA journal_mode = WAL")
    except sqlite3.DatabaseError:
        pass
    return c


@contextmanager
def 事务(c: sqlite3.Connection):
    """写事务：扫描、开腿态、刷卡命运、旁路匣同成败；跨连接串行化，禁止半截。"""
    c.execute("BEGIN IMMEDIATE")
    try:
        yield c
    except BaseException:
        c.execute("ROLLBACK")
        raise
    else:
        c.execute("COMMIT")
