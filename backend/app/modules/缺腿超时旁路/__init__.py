"""缺腿超时旁路：独立主链路。

全局口径（只贯彻一种）：**甲 · 保留已旁路开腿行**。
- 超时后开腿账行不删，状态置 `已旁路`，仍可按开腿键查到；
- 旁路匣以 `开腿键` 列指向该腿（载荷另带开腿快照，审计可对）；
- 开腿键查询返回 `是否仍在开腿表=True`；
- 超时后任何再推匹配出站都不得成对，只能落「超时后出站」旁路。

硬推理约束：超时旁路是异常链路复杂状态——扫描、开腿态、刷卡命运、旁路匣
同成败；同一进站不得既被旁路又落行程。因此扫描用条件更新
（`WHERE 状态='在途'`）抢占，成对写闸同样用条件更新抢占，二者互斥。

若将来切到乙（物理删除开腿行），只改本模块：`查腿` 对不存在行的分支
改为读旁路匣快照且 `是否仍在开腿表=False`；其余调用方无需改动。
"""
import json

from app.services import 时间

NAME = "缺腿超时旁路"

口径 = "保留已旁路开腿行"
开腿行保留 = True
旁路原因 = "缺腿超时"
追出原因 = "超时后出站"
判据 = "本批已见最大事件时 − 进站事件时 ≥ 最大行程秒"


def _最大行程秒(conn) -> int:
    row = conn.execute("SELECT 值 FROM 站规 WHERE 键='最大行程秒'").fetchone()
    try:
        return int(row["值"]) if row else 7200
    except (TypeError, ValueError):
        return 7200


def 写超时旁路(conn, 腿, 最大行程秒: int, 水位事件时: str, 处理时: str) -> int:
    """腿已被本函数调用方原子置为已旁路后，落旁路匣一行，返回旁路编号。"""
    历时 = 时间.差秒(腿["进站事件时"], 水位事件时)
    载荷 = {
        "口径": 口径,
        "开腿键": 腿["开腿键"],
        "开腿快照": {
            "开腿键": 腿["开腿键"],
            "卡号": 腿["卡号"],
            "进站事件编号": 腿["进站事件编号"],
            "进站站点键": 腿["进站站点键"],
            "进站事件时": 腿["进站事件时"],
        },
        "进站事件时": 腿["进站事件时"],
        "水位": 水位事件时,
        "最大行程秒": 最大行程秒,
        "历时秒": 历时,
    }
    cur = conn.execute(
        "INSERT INTO 旁路匣(原因, 卡号, 事件编号, 开腿键, 载荷, 时刻) VALUES (?,?,?,?,?,?)",
        (
            旁路原因,
            腿["卡号"],
            腿["进站事件编号"],
            腿["开腿键"],
            json.dumps(载荷, ensure_ascii=False),
            处理时,
        ),
    )
    return int(cur.lastrowid)


def _抢占旁路(conn, 腿, 最大行程秒: int, 水位事件时: str, 处理时: str) -> int | None:
    """原子把在途腿置已旁路；抢到才写旁路匣，返回旁路编号；没抢到返回 None。"""
    cur = conn.execute(
        "UPDATE 开腿账 SET 状态='已旁路', 更新处理时=? WHERE 开腿键=? AND 状态='在途'",
        (处理时, 腿["开腿键"]),
    )
    if cur.rowcount != 1:
        return None
    conn.execute(
        "UPDATE 刷卡点 SET 命运='已旁路' WHERE 事件编号=? AND 命运='已开腿'",
        (腿["进站事件编号"],),
    )
    return 写超时旁路(conn, 腿, 最大行程秒, 水位事件时, 处理时)


def 扫超时(conn, 最大行程秒: int, 水位事件时: str, 处理时: str) -> list[dict]:
    """水位推进后扫描：越过最大行程秒仍在途的开腿必须旁路。

    返回本次新旁路的明细（开腿键 / 进站事件编号 / 旁路编号），已旁路的不重复计。
    """
    if not 水位事件时:
        return []
    新旁 = []
    for 腿 in list(conn.execute("SELECT * FROM 开腿账 WHERE 状态='在途' ORDER BY 进站事件时 ASC")):
        历时 = 时间.差秒(腿["进站事件时"], 水位事件时)
        if 历时 < 最大行程秒:
            continue
        编号 = _抢占旁路(conn, 腿, 最大行程秒, 水位事件时, 处理时)
        if 编号 is None:  # 并发下已被成对或已被旁路：禁止半截
            continue
        新旁.append(
            {
                "开腿键": 腿["开腿键"],
                "卡号": 腿["卡号"],
                "事件编号": 腿["进站事件编号"],
                "旁路编号": 编号,
                "历时秒": 历时,
            }
        )
    return 新旁


def 扫超时数(conn, 最大行程秒: int, 水位事件时: str, 处理时: str) -> int:
    return len(扫超时(conn, 最大行程秒, 水位事件时, 处理时))


def 成对写出站(
    conn,
    腿,
    出站事件编号: str,
    出站站点键: str,
    出站事件时: str,
    处理时: str,
    最大行程秒: int,
) -> str | None:
    """出站成对写闸。

    返回行程键；返回 None 表示写闸拒绝（腿已不在途或历时越过上限），调用方
    必须把该出站落旁路，不得补写行程。条件更新 + 唯一索引保证同一进站不会
    既旁路又成对。
    """
    历时 = 时间.差秒(腿["进站事件时"], 出站事件时)
    if 历时 >= 最大行程秒:
        # 越界出站：腿仍在途则先原子旁路（与扫描同口径），再拒绝成对
        _抢占旁路(conn, 腿, 最大行程秒, 出站事件时, 处理时)
        return None

    cur = conn.execute(
        "UPDATE 开腿账 SET 状态='已成对', 更新处理时=? WHERE 开腿键=? AND 状态='在途'",
        (处理时, 腿["开腿键"]),
    )
    if cur.rowcount != 1:
        return None

    行程键 = f"行-{腿['进站事件编号']}-{出站事件编号}"
    conn.execute(
        """INSERT INTO 行程账(行程键,卡号,进站事件编号,出站事件编号,进站站点键,出站站点键,
           进站事件时,出站事件时,历时秒,状态,版本,处理时)
           VALUES (?,?,?,?,?,?,?,?,?,'已成对',1,?)""",
        (
            行程键,
            腿["卡号"],
            腿["进站事件编号"],
            出站事件编号,
            腿["进站站点键"],
            出站站点键,
            腿["进站事件时"],
            出站事件时,
            max(0, 历时),
            处理时,
        ),
    )
    conn.execute(
        "UPDATE 刷卡点 SET 命运='已成对', 行程键=? WHERE 事件编号 IN (?,?)",
        (行程键, 腿["进站事件编号"], 出站事件编号),
    )
    return 行程键


def 找超时腿(conn, 卡号: str):
    """找该卡最近一条已被缺腿超时旁路的开腿，用于拒绝再成对并留审计链。

    只认「该卡最后一条腿」：若超时旁路之后该卡又开过新腿，则再来的出站不属于
    被旁路的那条腿，按出站孤儿处理，不得张冠李戴。
    """
    return conn.execute(
        """SELECT l.* FROM 开腿账 l
             JOIN 旁路匣 b ON b.开腿键 = l.开腿键 AND b.原因 = ?
            WHERE l.卡号 = ? AND l.状态 = '已旁路'
              AND NOT EXISTS (
                    SELECT 1 FROM 开腿账 n
                     WHERE n.卡号 = l.卡号 AND n.开腿键 <> l.开腿键
                       AND n.进站事件时 >= l.进站事件时
              )
            ORDER BY l.进站事件时 DESC, b.编号 DESC
            LIMIT 1""",
        (旁路原因, 卡号),
    ).fetchone()


def 记追出(
    conn,
    腿,
    出站事件编号: str,
    出站站点键: str,
    出站事件时: str,
    处理时: str,
) -> int:
    """超时后仍推来匹配出站：落「超时后出站」旁路，明确拒绝成对。"""
    旁 = conn.execute(
        "SELECT 编号 FROM 旁路匣 WHERE 开腿键=? AND 原因=? ORDER BY 编号 DESC LIMIT 1",
        (腿["开腿键"], 旁路原因),
    ).fetchone()
    载荷 = {
        "口径": 口径,
        "开腿键": 腿["开腿键"],
        "进站事件编号": 腿["进站事件编号"],
        "进站事件时": 腿["进站事件时"],
        "出站事件编号": 出站事件编号,
        "出站站点键": 出站站点键,
        "出站事件时": 出站事件时,
        "历时秒": 时间.差秒(腿["进站事件时"], 出站事件时),
        "原旁路编号": 旁["编号"] if 旁 else None,
        "处置": "拒绝成对",
    }
    cur = conn.execute(
        "INSERT INTO 旁路匣(原因, 卡号, 事件编号, 开腿键, 载荷, 时刻) VALUES (?,?,?,?,?,?)",
        (
            追出原因,
            腿["卡号"],
            出站事件编号,
            腿["开腿键"],
            json.dumps(载荷, ensure_ascii=False),
            处理时,
        ),
    )
    return int(cur.lastrowid)


def 口径信息() -> dict:
    return {
        "口径": 口径,
        "开腿行保留": 开腿行保留,
        "旁路原因": 旁路原因,
        "追出原因": 追出原因,
        "判据": 判据,
        "只读": True,
        "说明": (
            "超时后开腿行保留为已旁路，仍可按开腿键查到；旁路匣指向开腿键；"
            "后续出站不得配该腿，只能落超时后出站旁路。"
        ),
    }


def _解析载荷(s: str) -> dict:
    try:
        v = json.loads(s or "{}")
        return v if isinstance(v, dict) else {"原载荷": v}
    except Exception:
        return {"原始": s}


def 查腿(conn, 开腿键: str) -> dict:
    """超时旁路只读核验：按开腿键查是否仍在开腿表、旁路编号、valid。

    valid = 超时旁路链路自洽（行保留、恰有一条缺腿超时旁路指向它、
    进站刷卡已旁路、未落行程、追出出站也未成对）。
    """
    查询键 = (开腿键 or "").strip()
    腿 = conn.execute("SELECT * FROM 开腿账 WHERE 开腿键=?", (查询键,)).fetchone()
    if not 腿 and 查询键 and not 查询键.startswith("腿-"):
        候选 = f"腿-{查询键}"
        腿 = conn.execute("SELECT * FROM 开腿账 WHERE 开腿键=?", (候选,)).fetchone()
        if 腿:
            查询键 = 候选

    旁 = conn.execute(
        "SELECT * FROM 旁路匣 WHERE 开腿键=? AND 原因=? ORDER BY 编号 DESC LIMIT 1",
        (查询键, 旁路原因),
    ).fetchone()
    追出 = list(
        conn.execute(
            "SELECT * FROM 旁路匣 WHERE 开腿键=? AND 原因=? ORDER BY 编号",
            (查询键, 追出原因),
        )
    )

    问题: list[str] = []
    行程 = None
    if not 腿:
        问题.append("开腿行不存在：保留口径下缺腿超时应保留已旁路行")
    else:
        if 腿["状态"] != "已旁路":
            问题.append(f"开腿行状态为{腿['状态']}，非已旁路")
        if not 旁:
            问题.append("旁路匣未指向该开腿键（缺腿超时旁路缺失）")
        刷卡 = conn.execute(
            "SELECT 命运 FROM 刷卡点 WHERE 事件编号=?", (腿["进站事件编号"],)
        ).fetchone()
        if not 刷卡 or 刷卡["命运"] != "已旁路":
            问题.append("进站刷卡命运非已旁路")
        行程 = conn.execute(
            "SELECT 行程键, 状态, 历时秒 FROM 行程账 WHERE 进站事件编号=? LIMIT 1",
            (腿["进站事件编号"],),
        ).fetchone()
        if 行程:
            问题.append(f"该腿已落行程{行程['行程键']}，旁路后又成对")

    后续出站 = []
    for r in 追出:
        d = _解析载荷(r["载荷"])
        出 = conn.execute(
            "SELECT 命运 FROM 刷卡点 WHERE 事件编号=?", (r["事件编号"],)
        ).fetchone()
        已入行程 = conn.execute(
            "SELECT 1 FROM 行程账 WHERE 出站事件编号=? LIMIT 1", (r["事件编号"],)
        ).fetchone()
        if not 出 or 出["命运"] != "已旁路":
            问题.append(f"追出{r['事件编号']}刷卡命运非已旁路")
        if 已入行程:
            问题.append(f"追出{r['事件编号']}竟已落行程")
        后续出站.append(
            {
                "旁路编号": r["编号"],
                "出站事件编号": r["事件编号"],
                "出站事件时": d.get("出站事件时", ""),
                "处置": d.get("处置", 追出原因),
                "原旁路编号": d.get("原旁路编号"),
                "刷卡命运": 出["命运"] if 出 else "无",
            }
        )

    return {
        "查询键": 查询键,
        "开腿键": 腿["开腿键"] if 腿 else 查询键,
        "口径": 口径,
        "是否仍在开腿表": bool(腿),
        "命中行": bool(腿),
        "状态": 腿["状态"] if 腿 else "无",
        "卡号": 腿["卡号"] if 腿 else (旁["卡号"] if 旁 else ""),
        "进站事件编号": 腿["进站事件编号"] if 腿 else (旁["事件编号"] if 旁 else ""),
        "进站站点键": 腿["进站站点键"] if 腿 else "",
        "进站事件时": 腿["进站事件时"] if 腿 else "",
        "旁路编号": 旁["编号"] if 旁 else None,
        "旁路原因": 旁["原因"] if 旁 else "",
        "旁路时刻": 旁["时刻"] if 旁 else "",
        "开腿快照": _解析载荷(旁["载荷"]).get("开腿快照") if 旁 else None,
        "成对行程键": 行程["行程键"] if 行程 else "",
        "是否再成对": bool(行程),
        "后续出站": 后续出站,
        "valid": not 问题,
        "说明": "链路自洽" if not 问题 else "；".join(问题)[:600],
    }
