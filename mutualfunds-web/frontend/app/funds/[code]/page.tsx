"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Spinner } from "@/components/Spinner";
import { ArrowLeft } from "lucide-react";
import {
  LineChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, Legend, CartesianGrid,
} from "recharts";

// ── Types ─────────────────────────────────────────────────────────────────────

interface NavPoint { date: string; nav: string; }
interface NiftyPoint { date: string; value: number; }
interface FundMeta { scheme_name: string; fund_house: string; scheme_category: string; }
interface Returns { [key: string]: number | null; }

interface FundDetail {
  meta: FundMeta;
  nav_data: NavPoint[];
  nifty_data: NiftyPoint[];
  returns: Returns;
}

interface SimilarFund {
  name: string;
  fund_house: string;
  returns: { "1y": number | null };
  volatility: number;
  max_drawdown: number;
  similarity_score: number;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const PERIODS: Record<string, number | null> = { "1Y": 365, "3Y": 1095, "5Y": 1825, "10Y": 3650, "Max": null };

// Parse DD-MM-YYYY → Date
function parseDate(s: string): Date {
  const [d, m, y] = s.split("-").map(Number);
  return new Date(y, m - 1, d);
}

// Format Date → DD-MM-YYYY (to match MFAPI date strings)
function fmtDate(d: Date): string {
  return `${String(d.getDate()).padStart(2,"0")}-${String(d.getMonth()+1).padStart(2,"0")}-${d.getFullYear()}`;
}

function buildChartData(
  navData: NavPoint[],
  niftyData: NiftyPoint[],
  days: number | null
) {
  // Sort nav oldest → newest
  const sorted = [...navData].sort((a, b) => parseDate(a.date).getTime() - parseDate(b.date).getTime());

  // Filter to selected period
  const cutoff = days ? new Date(Date.now() - days * 86400000) : null;
  const filtered = cutoff ? sorted.filter(d => parseDate(d.date) >= cutoff) : sorted;
  if (filtered.length === 0) return [];

  const fundBase = parseFloat(filtered[0].nav);

  // Nifty lookup map (same DD-MM-YYYY format from backend)
  const niftyMap = new Map<string, number>(niftyData.map(d => [d.date, d.value]));

  // Find nifty base at period start — walk up to 7 days for weekends/holidays
  let niftyBase: number | null = null;
  const startDt = parseDate(filtered[0].date);
  for (let i = 0; i <= 7; i++) {
    const key = fmtDate(new Date(startDt.getTime() + i * 86400000));
    if (niftyMap.has(key)) { niftyBase = niftyMap.get(key)!; break; }
  }

  return filtered.map(d => ({
    date: d.date,
    fund: parseFloat(((parseFloat(d.nav) / fundBase) * 100).toFixed(2)),
    nifty: niftyBase && niftyMap.has(d.date)
      ? parseFloat(((niftyMap.get(d.date)! / niftyBase) * 100).toFixed(2))
      : null,
  }));
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function FundPage() {
  const { code } = useParams<{ code: string }>();
  const router = useRouter();

  const [fund, setFund] = useState<FundDetail | null>(null);
  const [summary, setSummary] = useState<string>("");
  const [similar, setSimilar] = useState<SimilarFund[]>([]);
  const [similarLoaded, setSimilarLoaded] = useState(false);
  const [report, setReport] = useState<string>("");
  const [period, setPeriod] = useState("Max");
  const [messages, setMessages] = useState<{ role: string; content: string }[]>([]);
  const chatInputRef = useRef<HTMLInputElement>(null);
  const [chatLoading, setChatLoading] = useState(false);
  const [niftyReturns, setNiftyReturns] = useState<Returns>({});

  // Load fund detail
  useEffect(() => {
    if (!code) return;
    fetch(`/api/funds/${code}`)
      .then((r) => r.json())
      .then(setFund)
      .catch(console.error);

    fetch(`/api/funds/nifty/returns`)
      .then((r) => r.json())
      .then(setNiftyReturns)
      .catch(console.error);

    // Load summary + similar (don't need fund meta for these)
    fetch(`/api/funds/${code}/summary`)
      .then((r) => r.json())
      .then((d) => setSummary(d.summary))
      .catch(console.error);

    fetch(`/api/funds/${code}/similar`)
      .then((r) => r.json())
      .then((d) => { setSimilar(d.similar ?? []); setSimilarLoaded(true); })
      .catch(() => setSimilarLoaded(true));
  }, [code]);

  // Load report once fund meta is available (needs fund_house + scheme_name)
  useEffect(() => {
    if (!fund || !code) return;
    fetch(`/api/funds/${code}/report?fund_house=${encodeURIComponent(fund.meta.fund_house)}&scheme_name=${encodeURIComponent(fund.meta.scheme_name)}`)
      .then((r) => r.json())
      .then((d) => setReport(d.report ?? ""))
      .catch(console.error);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fund?.meta?.fund_house]);

  async function sendChat() {
    const input = chatInputRef.current?.value.trim() ?? "";
    if (!input || !fund) return;
    const userMsg = { role: "user", content: input };
    const newMessages = [...messages, userMsg];
    setMessages(newMessages);
    if (chatInputRef.current) chatInputRef.current.value = "";
    setChatLoading(true);
    try {
      const res = await fetch("/api/funds/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scheme_code: code,
          messages: newMessages,
          manager_info: report,
        }),
      });
      const data = await res.json();
      setMessages([...newMessages, { role: "assistant", content: data.response }]);
    } catch (e) {
      console.error(e);
    } finally {
      setChatLoading(false);
    }
  }

  const chartData = useMemo(
    () => fund ? buildChartData(fund.nav_data, fund.nifty_data ?? [], PERIODS[period]) : [],
    [fund, period]
  );

  if (!fund) {
    return (
      <div className="flex items-center gap-3 text-[#888] pt-20 justify-center">
        <Spinner size={24} /> Loading fund data...
      </div>
    );
  }

  const { meta, nav_data, nifty_data, returns } = fund;

  const returnPeriods = [
    { label: "1 Year", fundKey: "1 Year", niftyKey: "1 Year" },
    { label: "3 Year (CAGR)", fundKey: "3 Year", niftyKey: "3 Year" },
    { label: "5 Year (CAGR)", fundKey: "5 Year", niftyKey: "5 Year" },
    { label: "10 Year (CAGR)", fundKey: "10 Year", niftyKey: "10 Year" },
  ];

  return (
    <div className="space-y-10 pb-16">
      {/* Back */}
      <button
        onClick={() => router.back()}
        className="flex items-center gap-2 text-[#888] hover:text-white transition-colors text-sm"
      >
        <ArrowLeft size={16} /> Back
      </button>

      {/* Header + AI Summary side by side */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 items-start">
        {/* Left — fund info & NAV */}
        <div>
          <h1 className="text-2xl font-bold">{meta.scheme_name}</h1>
          <p className="text-[#888] mt-1">{meta.fund_house} · {meta.scheme_category}</p>
          <p className="text-[#00ff88] font-bold text-2xl mt-3">
            ₹{parseFloat(nav_data[0]?.nav ?? "0").toLocaleString("en-IN", { minimumFractionDigits: 2 })}
            <span className="text-[#888] text-sm font-normal ml-2">Current NAV</span>
          </p>
        </div>

        {/* Right — AI Summary */}
        <div className="bg-[#111] border border-[#2a2a2a] rounded-xl p-5">
          <h2 className="text-sm font-semibold text-[#888] uppercase tracking-wide mb-2">AI Summary</h2>
          {summary ? (
            <p className="text-[#ccc] text-sm leading-relaxed">{summary}</p>
          ) : (
            <div className="flex gap-2 items-center text-[#888] text-sm"><Spinner /> Generating...</div>
          )}
        </div>
      </div>

      {/* Chart */}
      <section>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">Performance vs Nifty 50</h2>
          <div className="flex gap-1">
            {Object.keys(PERIODS).map((p) => (
              <button
                key={p}
                onClick={() => setPeriod(p)}
                className={`px-3 py-1 rounded-md text-sm transition-colors ${
                  period === p ? "bg-[#1a1a1a] text-white" : "text-[#888] hover:text-white"
                }`}
              >
                {p}
              </button>
            ))}
          </div>
        </div>
        <div className="bg-[#111] border border-[#2a2a2a] rounded-xl p-4">
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={chartData} margin={{ bottom: 40, left: 0, right: 10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e1e1e" />
              <XAxis
                dataKey="date"
                tick={{ fill: "#aaa", fontSize: 10 }}
                tickLine={false}
                interval="preserveStartEnd"
                angle={-35}
                textAnchor="end"
                height={55}
              />
              <YAxis tick={{ fill: "#aaa", fontSize: 11 }} tickLine={false} axisLine={false} />
              <Tooltip
                contentStyle={{ background: "#1a1a1a", border: "1px solid #2a2a2a", borderRadius: 8 }}
                labelStyle={{ color: "#888" }}
                formatter={(v, name) => [`${v}`, name as string]}
              />
              <Legend wrapperStyle={{ color: "#aaa", fontSize: 12 }} />
              <Line type="monotone" dataKey="fund" name={meta.scheme_name.slice(0, 25)} stroke="#00ff88" dot={false} strokeWidth={2} connectNulls />
              <Line type="monotone" dataKey="nifty" name="Nifty 50" stroke="#4da6ff" dot={false} strokeWidth={1.5} strokeDasharray="4 2" connectNulls />
            </LineChart>
          </ResponsiveContainer>
          <p className="text-[#555] text-xs mt-1 text-center">Both normalized to 100 at start of selected period</p>
        </div>
      </section>

      {/* Returns table */}
      <section>
        <h2 className="text-lg font-semibold mb-4">Returns Comparison</h2>
        <div className="bg-[#111] border border-[#2a2a2a] rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#2a2a2a]">
                <th className="text-left px-4 py-3 text-[#888] font-medium">Period</th>
                <th className="text-right px-4 py-3 text-[#888] font-medium">Fund Return</th>
                <th className="text-right px-4 py-3 text-[#888] font-medium">Nifty 50</th>
                <th className="text-right px-4 py-3 text-[#888] font-medium">Outperformance</th>
              </tr>
            </thead>
            <tbody>
              {returnPeriods.map(({ label, fundKey, niftyKey }) => {
                const fr = returns[fundKey] ?? null;
                const nr = niftyReturns[niftyKey] ?? null;
                const diff = fr !== null && nr !== null ? parseFloat((fr - nr).toFixed(2)) : null;
                const diffColor = diff === null ? "#888" : diff >= 0 ? "#00ff88" : "#ff4444";
                return (
                  <tr key={label} className="border-b border-[#1a1a1a] last:border-0">
                    <td className="px-4 py-3 text-[#aaa]">{label}</td>
                    <td className="px-4 py-3 text-right font-medium" style={{ color: fr && fr > 0 ? "#00ff88" : "#ff4444" }}>
                      {fr !== null ? `${fr}%` : "—"}
                    </td>
                    <td className="px-4 py-3 text-right text-[#888]">{nr !== null ? `${nr}%` : "—"}</td>
                    <td className="px-4 py-3 text-right font-medium" style={{ color: diffColor }}>
                      {diff !== null ? `${diff > 0 ? "+" : ""}${diff}%` : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="text-[#555] text-xs px-4 py-2">1Y is absolute return. 3Y/5Y/10Y are CAGR.</p>
        </div>
      </section>

      {/* Similar Funds */}
      <section>
        <h2 className="text-lg font-semibold mb-2">🔍 Similar Funds</h2>
        <p className="text-[#888] text-sm mb-4">Funds with similar return profile and risk characteristics</p>
        {!similarLoaded ? (
          <div className="flex gap-2 items-center text-[#888]"><Spinner /> Finding similar funds...</div>
        ) : similar.length === 0 ? (
          <div className="bg-[#111] rounded-xl p-6 border border-[#2a2a2a] text-center text-[#888]">
            <p className="text-2xl mb-2">🔍</p>
            <p className="font-medium text-white mb-1">No similar funds found</p>
            <p className="text-sm">This fund is not yet part of our similarity index.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {similar.map((f) => {
              const r1y = f.returns?.["1y"] ?? null;
              const color = r1y && r1y > 0 ? "#00ff88" : "#ff4444";
              const borderColor = f.similarity_score < 50 ? "#555" : color;
              return (
                <div key={f.name} className="bg-[#111] rounded-xl p-4 border-l-[3px]" style={{ borderLeftColor: borderColor }}>
                  <p className="text-[#888] text-xs mb-1">{f.fund_house}</p>
                  <p className="font-semibold text-sm mb-3">{f.name.slice(0, 50)}…</p>
                  <div className="space-y-1 text-sm">
                    <div className="flex justify-between">
                      <span className="text-[#888]">1Y Return</span>
                      <span style={{ color }}>{r1y !== null ? `${r1y}%` : "—"}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-[#888]">Volatility</span>
                      <span className="text-white">{f.volatility}%</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-[#888]">Max Drawdown</span>
                      <span className="text-[#ff9944]">{f.max_drawdown}%</span>
                    </div>
                    <div className="text-center bg-[#1a1a1a] rounded py-1 mt-2 text-xs" style={{ color: f.similarity_score < 50 ? "#888" : "#4da6ff" }}>
                      {f.similarity_score < 50 ? "⚠ Limited similarity" : `Similarity: ${f.similarity_score}%`}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* Fund Report */}
      {report && (
        <section>
          <h2 className="text-lg font-semibold mb-3">📄 Fund Report</h2>
          <div className="bg-[#111] border border-[#2a2a2a] rounded-xl p-5">
            <pre className="text-[#ccc] text-sm whitespace-pre-wrap font-sans leading-relaxed">{report}</pre>
          </div>
        </section>
      )}

      {/* Chat */}
      <section>
        <h2 className="text-lg font-semibold mb-1">💬 Ask Anything About This Fund</h2>
        <p className="text-[#888] text-sm mb-4">Powered by AI — ask about performance, risk, fund manager, suitability</p>

        <div className="bg-[#111] border border-[#2a2a2a] rounded-xl flex flex-col" style={{ minHeight: 200 }}>
          {/* Messages */}
          <div className="flex-1 p-4 space-y-3 overflow-y-auto max-h-80">
            {messages.length === 0 && (
              <p className="text-[#555] text-sm">No messages yet. Ask something below.</p>
            )}
            {messages.map((m, i) => (
              <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                <div
                  className={`max-w-[80%] rounded-xl px-4 py-2.5 text-sm leading-relaxed ${
                    m.role === "user"
                      ? "bg-[#1a1a1a] text-white"
                      : "bg-[#0f2a1a] text-[#00ff88] border border-[#1a3a2a]"
                  }`}
                >
                  {m.content}
                </div>
              </div>
            ))}
            {chatLoading && (
              <div className="flex justify-start">
                <div className="bg-[#1a1a1a] rounded-xl px-4 py-2.5 flex gap-2 items-center text-[#888] text-sm">
                  <Spinner size={14} /> Thinking...
                </div>
              </div>
            )}
          </div>

          {/* Input */}
          <div className="border-t border-[#2a2a2a] flex items-center px-4 py-3 gap-3">
            <input
              ref={chatInputRef}
              className="flex-1 bg-transparent outline-none text-sm text-white placeholder-[#555]"
              placeholder="Ask something about this fund..."
              defaultValue=""
              disabled={chatLoading}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.repeat && !chatLoading) sendChat();
              }}
            />
            <button
              onClick={sendChat}
              disabled={chatLoading}
              className="text-sm px-4 py-1.5 rounded-lg bg-[#00ff88] text-black font-semibold disabled:opacity-40 hover:bg-[#00dd77] transition-colors"
            >
              Send
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
