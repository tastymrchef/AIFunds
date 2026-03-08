"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Upload, Lock, TrendingUp, TrendingDown, ChevronDown, ChevronUp, ExternalLink } from "lucide-react";
import { Spinner } from "@/components/Spinner";

// ── Types ─────────────────────────────────────────────────────────────────────

interface Transaction {
  date: string;
  type: string;
  amount: number;
  units: number;
  nav: number;
}

interface Holding {
  amc: string;
  folio: string;
  scheme: string;
  scheme_code: string;
  isin: string;
  units: number;
  avg_nav: number;
  cost_value: number;
  live_nav: number;
  live_value: number;
  abs_return_pct: number;
  xirr_pct: number | null;
  transactions: Transaction[];
}

interface PortfolioSummary {
  total_invested: number;
  total_current: number;
  total_gain: number;
  overall_return_pct: number;
  fund_count: number;
}

interface PortfolioData {
  investor: { name: string; email: string; pan: string };
  summary: PortfolioSummary;
  holdings: Holding[];
}

// ── helpers ───────────────────────────────────────────────────────────────────

function fmt(n: number) {
  return new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 }).format(n);
}
function fmtCurrency(n: number) {
  return "₹" + fmt(n);
}
function pctColor(v: number) {
  return v >= 0 ? "#00ff88" : "#ff4444";
}
function pctStr(v: number | null) {
  if (v === null || v === undefined) return "—";
  return (v >= 0 ? "+" : "") + v.toFixed(2) + "%";
}

// ── Upload panel ──────────────────────────────────────────────────────────────

function UploadPanel({ onParsed }: { onParsed: (data: PortfolioData) => void }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile]         = useState<File | null>(null);
  const [password, setPassword] = useState("");
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file || !password) return;
    setLoading(true);
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("password", password);
      const res = await fetch("/api/portfolio/parse-cas", { method: "POST", body: form });
      const json = await res.json();
      if (!res.ok) throw new Error(json.detail || "Failed to parse PDF");
      onParsed(json);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-lg mx-auto mt-10">
      <div className="text-center mb-8">
        <h1 className="text-3xl font-bold mb-2">📂 My Portfolio</h1>
        <p className="text-[#888]">Upload your CAS PDF to analyse your mutual fund portfolio</p>
      </div>

      {/* How to get CAS */}
      <div className="bg-[#111] border border-[#2a2a2a] rounded-xl p-4 mb-6 text-sm space-y-1">
        <p className="font-semibold text-[#aaa] mb-2">How to get your CAS PDF</p>
        <p className="text-[#666]">1. Go to <a href="https://www.camsonline.com" target="_blank" rel="noopener noreferrer" className="text-[#4da6ff] hover:underline">camsonline.com <ExternalLink size={10} className="inline" /></a></p>
        <p className="text-[#666]">2. Investor Services → Mailback Services → Consolidated Account Statement</p>
        <p className="text-[#666]">3. Enter your registered email — PDF lands in your inbox</p>
        <p className="text-[#666]">4. Password = PAN (uppercase) + date of birth as DDMMYYYY<br /><span className="text-[#555] ml-4">e.g. ABCDE1234F01011990</span></p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        {/* File drop zone */}
        <div
          onClick={() => fileRef.current?.click()}
          className="border-2 border-dashed border-[#2a2a2a] hover:border-[#00ff88] rounded-xl p-8 text-center cursor-pointer transition-colors"
        >
          <Upload size={28} className="mx-auto mb-2 text-[#555]" />
          {file
            ? <p className="text-white font-medium">{file.name}</p>
            : <p className="text-[#555]">Click to select your CAS PDF</p>
          }
          <input
            ref={fileRef}
            type="file"
            accept=".pdf"
            className="hidden"
            onChange={e => setFile(e.target.files?.[0] ?? null)}
          />
        </div>

        {/* Password */}
        <div className="flex items-center bg-[#111] border border-[#2a2a2a] rounded-xl px-4 py-3 gap-3 focus-within:border-[#00ff88] transition-colors">
          <Lock size={16} className="text-[#555] shrink-0" />
          <input
            type="password"
            placeholder="PDF password (PAN + DOB, e.g. ABCDE1234F01011990)"
            value={password}
            onChange={e => setPassword(e.target.value)}
            className="flex-1 bg-transparent outline-none text-white placeholder-[#555] text-sm"
          />
        </div>

        {error && <p className="text-[#ff4444] text-sm">{error}</p>}

        <button
          type="submit"
          disabled={!file || !password || loading}
          className="w-full bg-[#00ff88] text-black font-semibold py-3 rounded-xl hover:bg-[#00dd77] transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2"
        >
          {loading ? <><Spinner /> Parsing your portfolio...</> : "Analyse Portfolio"}
        </button>
      </form>
    </div>
  );
}

// ── Dashboard ─────────────────────────────────────────────────────────────────

function HoldingRow({ h }: { h: Holding }) {
  const [open, setOpen] = useState(false);
  const isPos = h.abs_return_pct >= 0;

  return (
    <>
      <tr
        className="border-b border-[#1a1a1a] hover:bg-[#111] cursor-pointer transition-colors"
        onClick={() => setOpen(o => !o)}
      >
        <td className="py-3 px-4">
          <p className="text-sm text-white">{h.scheme.length > 55 ? h.scheme.slice(0, 55) + "…" : h.scheme}</p>
          <p className="text-xs text-[#555] mt-0.5">{h.amc} · Folio {h.folio}</p>
        </td>
        <td className="py-3 px-4 text-right text-sm text-[#aaa]">{fmt(h.units)}</td>
        <td className="py-3 px-4 text-right text-sm text-[#aaa]">{fmtCurrency(h.avg_nav)}</td>
        <td className="py-3 px-4 text-right text-sm text-[#aaa]">{fmtCurrency(h.live_nav)}</td>
        <td className="py-3 px-4 text-right text-sm font-medium text-white">{fmtCurrency(h.live_value)}</td>
        <td className="py-3 px-4 text-right text-sm font-semibold" style={{ color: pctColor(h.abs_return_pct) }}>
          {pctStr(h.abs_return_pct)}
        </td>
        <td className="py-3 px-4 text-right text-sm" style={{ color: h.xirr_pct !== null ? pctColor(h.xirr_pct) : "#555" }}>
          {pctStr(h.xirr_pct)}
        </td>
        <td className="py-3 px-4 text-[#555]">
          {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </td>
      </tr>

      {/* Transactions expand */}
      {open && h.transactions.length > 0 && (
        <tr className="bg-[#0d0d0d]">
          <td colSpan={8} className="px-6 py-3">
            <p className="text-xs font-semibold text-[#555] mb-2 uppercase tracking-wider">Transaction History</p>
            <table className="w-full text-xs">
              <thead>
                <tr className="text-[#555]">
                  <th className="text-left pb-1">Date</th>
                  <th className="text-left pb-1">Type</th>
                  <th className="text-right pb-1">Amount</th>
                  <th className="text-right pb-1">Units</th>
                  <th className="text-right pb-1">NAV</th>
                </tr>
              </thead>
              <tbody>
                {h.transactions.map((t, i) => (
                  <tr key={i} className="text-[#888] border-t border-[#1a1a1a]">
                    <td className="py-1">{t.date}</td>
                    <td className="py-1">{t.type}</td>
                    <td className="py-1 text-right">{fmtCurrency(t.amount)}</td>
                    <td className="py-1 text-right">{fmt(t.units)}</td>
                    <td className="py-1 text-right">{fmt(t.nav)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </td>
        </tr>
      )}
    </>
  );
}

function Dashboard({ data, onReset }: { data: PortfolioData; onReset: () => void }) {
  const { investor, summary, holdings } = data;
  const isPos = summary.overall_return_pct >= 0;

  // sort by live value descending
  const sorted = [...holdings].sort((a, b) => b.live_value - a.live_value);

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold">
            {investor.name ? `${investor.name}'s Portfolio` : "My Portfolio"}
          </h1>
          {investor.pan && <p className="text-[#555] text-sm mt-0.5">PAN: {investor.pan}</p>}
        </div>
        <button onClick={onReset} className="text-xs text-[#555] hover:text-[#888] border border-[#2a2a2a] px-3 py-1.5 rounded-lg transition-colors">
          Upload new CAS
        </button>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "Total Invested",  value: fmtCurrency(summary.total_invested),  sub: `${summary.fund_count} funds` },
          { label: "Current Value",   value: fmtCurrency(summary.total_current),   sub: "live NAV" },
          { label: "Total Gain/Loss", value: fmtCurrency(Math.abs(summary.total_gain)),
            sub: summary.total_gain >= 0 ? "profit" : "loss",
            color: pctColor(summary.total_gain) },
          { label: "Overall Return",  value: pctStr(summary.overall_return_pct),   sub: "absolute",
            color: pctColor(summary.overall_return_pct) },
        ].map(c => (
          <div key={c.label} className="bg-[#111] border border-[#2a2a2a] rounded-xl px-4 py-3">
            <p className="text-xs text-[#555] mb-1">{c.label}</p>
            <p className="text-xl font-bold" style={{ color: c.color ?? "white" }}>{c.value}</p>
            <p className="text-xs text-[#555] mt-0.5">{c.sub}</p>
          </div>
        ))}
      </div>

      {/* Holdings table */}
      <div>
        <h2 className="text-lg font-semibold mb-3">Holdings</h2>
        <div className="overflow-x-auto rounded-xl border border-[#2a2a2a]">
          <table className="w-full">
            <thead>
              <tr className="border-b border-[#2a2a2a] text-[#555] text-xs uppercase tracking-wider">
                <th className="text-left py-3 px-4">Fund</th>
                <th className="text-right py-3 px-4">Units</th>
                <th className="text-right py-3 px-4">Avg NAV</th>
                <th className="text-right py-3 px-4">Live NAV</th>
                <th className="text-right py-3 px-4">Value</th>
                <th className="text-right py-3 px-4">Return</th>
                <th className="text-right py-3 px-4">XIRR</th>
                <th className="py-3 px-4" />
              </tr>
            </thead>
            <tbody>
              {sorted.map((h, i) => <HoldingRow key={i} h={h} />)}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-[#555] mt-2">Click any row to see transaction history · NAVs fetched live from MFAPI</p>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function PortfolioPage() {
  const [data, setData] = useState<PortfolioData | null>(null);

  return (
    <div className="pb-12">
      {data
        ? <Dashboard data={data} onReset={() => setData(null)} />
        : <UploadPanel onParsed={setData} />
      }
    </div>
  );
}
