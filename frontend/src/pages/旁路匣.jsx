import React, { useEffect, useState } from "react";
import { 取 } from "../api.js";

const 原因选项 = ["", "缺腿超时", "超时后出站", "出站孤儿", "重复进站", "未知站点", "方向非法"];

export default function 旁路匣() {
  const [行, 设] = useState([]);
  const [原因, 设原因] = useState("");
  const [键, 设键] = useState("");
  const [查, 设查] = useState(null);
  const [讯, 设讯] = useState("");
  const 刷 = () => {
    const q = new URLSearchParams();
    if (原因) q.set("原因", 原因);
    if (键.trim()) q.set("开腿键", 键.trim().startsWith("腿-") ? 键.trim() : `腿-${键.trim()}`);
    const qs = q.toString();
    取(`/旁路匣${qs ? `?${qs}` : ""}`).then(设);
  };
  useEffect(() => { 刷(); }, [原因]);
  const 查腿 = async (候选) => {
    设讯("");
    设查(null);
    const 原 = (typeof 候选 === "string" ? 候选 : 键).trim();
    const k = !原 ? "" : 原.startsWith("腿-") ? 原 : `腿-${原}`;
    if (!k) { 设讯("先填开腿键，如 腿-t1"); return; }
    try { 设查(await 取(`/缺腿超时/查腿?开腿键=${encodeURIComponent(k)}`)); }
    catch (e) { 设讯(String(e.message || e)); }
  };
  return (
    <div>
      <h1 className="题">旁路匣</h1>
      <p className="述">
        缺腿超时、超时后出站、出站孤儿、重复进站、未知站等旁路原因。保留口径：超时后开腿行
        仍在开腿表（状态已旁路），旁路匣以开腿键指向它；超时后再推的匹配出站落「超时后出站」。
      </p>
      <div className="行">
        <select value={原因} onChange={(e) => 设原因(e.target.value)}>
          {原因选项.map((r) => <option key={r} value={r}>{r || "全部原因"}</option>)}
        </select>
        <input
          placeholder="开腿键，如 腿-t1"
          value={键}
          onChange={(e) => 设键(e.target.value)}
          style={{ minWidth: 180 }}
        />
        <button className="次" onClick={刷}>按匣刷新</button>
        <button className="次 亮片" onClick={() => 查腿()}>超时只读核验</button>
      </div>
      {讯 && <p className="讯">{讯}</p>}
      {查 && (
        <div className="段">
          <div className="段题">
            开腿键 {查.开腿键} · 口径 {查.口径}
            <span className={`徽章 ${查.valid ? "通" : "败"}`} style={{ marginLeft: 8 }}>
              {查.valid ? "链路自洽" : "链路撕裂"}
            </span>
          </div>
          <table>
            <thead><tr><th>是否仍在开腿表</th><th>状态</th><th>旁路编号</th><th>旁路原因</th><th>是否再成对</th><th>后续出站</th></tr></thead>
            <tbody>
              <tr>
                <td>{查.是否仍在开腿表 ? "是（命中行）" : "否（查无）"}</td>
                <td>{查.状态}</td>
                <td>{查.旁路编号 ?? "—"}</td>
                <td>{查.旁路原因 || "—"}</td>
                <td>{查.是否再成对 ? "是（异常）" : "否"}</td>
                <td>{查.后续出站?.length ? 查.后续出站.map((x) => `${x.出站事件编号}(${x.处置})`).join("、") : "—"}</td>
              </tr>
            </tbody>
          </table>
          <p className="讯" style={{ marginTop: 6 }}>{查.说明}</p>
        </div>
      )}
      {!行.length ? <div className="空态">旁路匣空。</div> : (
        <table>
          <thead><tr><th>#</th><th>原因</th><th>卡号</th><th>事件</th><th>开腿键</th><th>时刻</th><th>载荷</th></tr></thead>
          <tbody>
            {行.map((r) => (
              <tr key={r.编号}>
                <td>{r.编号}</td><td>{r.原因}</td><td>{r.卡号}</td>
                <td>{r.事件编号}</td>
                <td>
                  {r.开腿键 ? (
                    <a href="#" onClick={(e) => { e.preventDefault(); 设键(r.开腿键); 查腿(r.开腿键); }}>
                      {r.开腿键}
                    </a>
                  ) : "—"}
                </td>
                <td>{r.时刻}</td>
                <td style={{ maxWidth: 360, wordBreak: "break-all" }}>{r.载荷}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

