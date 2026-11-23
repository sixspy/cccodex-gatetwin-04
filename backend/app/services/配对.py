"""配对与缺腿超时：实现收敛到 `缺腿超时旁路` 模块，保证扫描与成对写闸同口径。"""
from app.modules.缺腿超时旁路 import (  # noqa: F401
    扫超时,
    扫超时数,
    找超时腿,
    记追出,
    写超时旁路,
    成对写出站,
    查腿,
    口径信息,
)
from app.services import 时间


def 扫缺腿超时(conn, 最大行程秒: int, 水位事件时: str, 处理时: str) -> int:
    """水位推进后，把超最大行程秒仍在途的开腿打进旁路；返回本次新旁路条数。"""
    return 扫超时数(conn, 最大行程秒, 水位事件时, 处理时)


def 成对写出站出站(conn, 开腿, 出站事件编号: str, 出站站点键: str, 出站事件时: str, 处理时: str):
    最大行程秒 = int(
        (conn.execute("SELECT 值 FROM 站规 WHERE 键='最大行程秒'").fetchone() or {"值": "7200"})["值"]
    )
    return 成对写出站(
        conn, 开腿, 出站事件编号, 出站站点键, 出站事件时, 处理时, 最大行程秒
    )
