import sqlite3
from datetime import datetime, timezone

from app.db import 连接, 事务

建表 = """
CREATE TABLE IF NOT EXISTS 站规 (
  键 TEXT PRIMARY KEY,
  值 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS 线路 (
  线路键 TEXT PRIMARY KEY,
  名称 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS 站点 (
  站点键 TEXT PRIMARY KEY,
  线路键 TEXT NOT NULL REFERENCES 线路(线路键),
  站名 TEXT NOT NULL,
  站序 INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS 刷卡点 (
  事件编号 TEXT PRIMARY KEY,
  卡号 TEXT NOT NULL,
  站点键 TEXT NOT NULL,
  方向 TEXT NOT NULL,
  事件时 TEXT NOT NULL,
  处理时 TEXT NOT NULL,
  命运 TEXT NOT NULL DEFAULT '已入流',
  行程键 TEXT NOT NULL DEFAULT '',
  批次编号 TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS 装载批次 (
  编号 TEXT PRIMARY KEY,
  时刻 TEXT NOT NULL,
  报告 TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS 开腿账 (
  开腿键 TEXT PRIMARY KEY,
  卡号 TEXT NOT NULL,
  进站事件编号 TEXT NOT NULL,
  进站站点键 TEXT NOT NULL,
  进站事件时 TEXT NOT NULL,
  状态 TEXT NOT NULL DEFAULT '在途',
  更新处理时 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS 行程账 (
  行程键 TEXT PRIMARY KEY,
  卡号 TEXT NOT NULL,
  进站事件编号 TEXT NOT NULL,
  出站事件编号 TEXT NOT NULL,
  进站站点键 TEXT NOT NULL,
  出站站点键 TEXT NOT NULL,
  进站事件时 TEXT NOT NULL,
  出站事件时 TEXT NOT NULL,
  历时秒 INTEGER NOT NULL DEFAULT 0,
  状态 TEXT NOT NULL DEFAULT '已成对',
  版本 INTEGER NOT NULL DEFAULT 1,
  处理时 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS 旁路匣 (
  编号 INTEGER PRIMARY KEY AUTOINCREMENT,
  原因 TEXT NOT NULL,
  卡号 TEXT NOT NULL DEFAULT '',
  事件编号 TEXT NOT NULL DEFAULT '',
  开腿键 TEXT NOT NULL DEFAULT '',
  载荷 TEXT NOT NULL,
  时刻 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS 行程贯验 (
  编号 INTEGER PRIMARY KEY AUTOINCREMENT,
  时刻 TEXT NOT NULL,
  刷卡数 INTEGER NOT NULL,
  行程数 INTEGER NOT NULL,
  开腿数 INTEGER NOT NULL,
  旁路数 INTEGER NOT NULL,
  是否通过 INTEGER NOT NULL,
  说明 TEXT NOT NULL
);
"""


def 此刻() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _迁移(conn) -> None:
    """幂等补列/补索引：旧库（无 开腿键 列）也能升到缺腿超时旁路口径。"""
    with 事务(conn):
        列 = {r["name"] for r in conn.execute("PRAGMA table_info(旁路匣)")}
        if "开腿键" not in 列:
            conn.execute("ALTER TABLE 旁路匣 ADD COLUMN 开腿键 TEXT NOT NULL DEFAULT ''")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_旁路匣_开腿键 ON 旁路匣(开腿键, 原因)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_开腿账_卡号状态 ON 开腿账(卡号, 状态)"
        )
        # 同一进站只能落一笔行程：扫描与成对写闸并发时由库兜底。
        # 旧库若已有重复数据，建索引失败不阻断启动（贯验会报出问题）。
        try:
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_行程账_进站事件编号 ON 行程账(进站事件编号)"
            )
        except sqlite3.IntegrityError:
            pass
        # 同一开腿只允许一条缺腿超时旁路
        conn.execute(
            """CREATE UNIQUE INDEX IF NOT EXISTS ux_旁路匣_缺腿超时
               ON 旁路匣(开腿键) WHERE 原因='缺腿超时' AND 开腿键<>''"""
        )
        conn.execute(
            "INSERT OR IGNORE INTO 站规(键, 值) VALUES ('缺腿超时口径', '保留已旁路开腿行')"
        )


def 初始化库() -> None:
    conn = 连接()
    conn.executescript(建表)
    _迁移(conn)
    with 事务(conn):
        if conn.execute("SELECT COUNT(*) AS c FROM 站规").fetchone()["c"] == 0:
            for k, v in {
                "站名": "闸对",
                "最大行程秒": "7200",
                "同站进出": "允许",
                "重复进站策略": "旧腿旁路并开新腿",
                "配对策略": "同卡先进后出",
                "缺腿超时口径": "保留已旁路开腿行",
                "骨架": "刷卡点装载→同卡进站出站成对物化→缺腿异向超时旁路→行程账与刷卡点互证",
            }.items():
                conn.execute("INSERT INTO 站规(键, 值) VALUES (?, ?)", (k, v))
        if conn.execute("SELECT COUNT(*) AS c FROM 线路").fetchone()["c"] == 0:
            conn.execute("INSERT INTO 线路(线路键, 名称) VALUES (?, ?)", ("线1", "一号线"))
            for i, (k, n) in enumerate(
                [("站A", "城东站"), ("站B", "中心站"), ("站C", "河西站")], start=1
            ):
                conn.execute(
                    "INSERT INTO 站点(站点键, 线路键, 站名, 站序) VALUES (?,?,?,?)",
                    (k, "线1", n, i),
                )
    conn.close()
