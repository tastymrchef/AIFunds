"use client";

import { useState, useEffect, useRef } from "react";
import { Search } from "lucide-react";
import { Spinner } from "@/components/Spinner";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
} from "recharts";

interface StockMatch {
  display_name: string;
  stock_key: string;
  fund_count: number;
}

interface FundHolding {
  scheme_name: string;
  fund_house: string;
  weight: number;
}

interface StockDetail {
  display_name: string;
  total_funds: number;
  funds: FundHolding[];
}

function weightColor(w: number) {
  if (w >= 3) return "#00ff88";
  if (w >= 1) return "#ff9944";
  return "#555";
}

export default function StocksPage() {
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<StockMatch[]>([]);
  const [selected, setSelected] = useState<StockDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [showDropdown, setShowDropdown] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!query.trim()) {
      setSuggestions([]);
      return;
    }
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      setLoading(true);
      fetch(`/api/holdings/search?q=${encodeURIComponent(query)}`)
        .then((r) => r.json())
        .then((d) => {
          setSuggestions(d.matches ?? []);
          setShowDropdown(true);
        })
        .catch(console.error)
        .finally(() => setLoading(false));
    }, 300);
  }, [query]);

  function selectStock(match: StockMatch) {
    setQuery(match.display_name);
    setShowDropdown(false);
    setSuggestions([]);
    setDetailLoading(true);
    fetch(`/api/holdings/stock/${match.stock_key}`)
      .then((r) => r.json())
      .then(setSelected)
      .catch(console.error)
      .finally(() => setDetailLoading(false));
  }

  const chartData = selected
    ? selected.funds.slice(0, 15).map((f) => ({
        name: f.scheme_name.replace(/(Direct|Growth|Plan|IDCW|Fund)/gi, "").trim().slice(0, 20),
        weight: f.weight,
        full_name: f.scheme_name,
      }))
    : [];

  return (
    <div className="space-y-8 pt-4">
      <div>
        <h1 className="text-2xl font-bold">Find Funds by Stock</h1>
        <p className="text-[#888] mt-1">Search any stock / company and see which mutual funds hold it</p>
      </div>

      {/* Search input */}
      <div className="max-w-xl relative">
        <div className="flex items-center gap-3 bg-[#111] border border-[#2a2a2a] rounded-xl px-4 py-3">
          <Search size={18} className="text-[#555]" />
          <input
            ref={inputRef}
            autoFocus
            className="flex-1 bg-transparent outline-none text-white placeholder-[#555]"
            placeholder="e.g. HDFC Bank, Infosys, Reliance..."
            value={query}
            onChange={(e) => { setQuery(e.target.value); setSelected(null); }}
            onFocus={() => suggestions.length > 0 && setShowDropdown(true)}
            onBlur={() => setTimeout(() => setShowDropdown(false), 150)}
          />
          {loading && <Spinner size={16} />}
        </div>

        {/* Dropdown */}
        {showDropdown && suggestions.length > 0 && (
          <div className="absolute top-full mt-1 w-full bg-[#111] border border-[#2a2a2a] rounded-xl overflow-hidden z-50 shadow-xl">
            {suggestions.map((s) => (
              <button
                key={s.stock_key}
                onMouseDown={() => selectStock(s)}
                className="w-full text-left px-4 py-3 hover:bg-[#1a1a1a] flex justify-between items-center transition-colors"
              >
                <span className="text-white">{s.display_name}</span>
                <span className="text-[#555] text-xs">{s.fund_count} fund{s.fund_count !== 1 ? "s" : ""}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {detailLoading && (
        <div className="flex gap-3 items-center text-[#888] pt-8 justify-center">
          <Spinner size={22} /> Loading holdings data...
        </div>
      )}

      {selected && !detailLoading && (
        <div className="space-y-8">
          {/* Summary */}
          <div>
            <h2 className="text-xl font-semibold">{selected.display_name}</h2>
            <p className="text-[#888] mt-1">{selected.total_funds} mutual funds hold this stock</p>
          </div>

          {/* Bar chart */}
          <section>
            <h3 className="text-base font-semibold mb-4">Top 15 Holdings by Weight</h3>
            <div className="bg-[#111] border border-[#2a2a2a] rounded-xl p-4">
              <ResponsiveContainer width="100%" height={320}>
                <BarChart data={chartData} layout="vertical" margin={{ left: 10, right: 40 }}>
                  <XAxis type="number" unit="%" tick={{ fill: "#555", fontSize: 11 }} tickLine={false} />
                  <YAxis type="category" dataKey="name" tick={{ fill: "#888", fontSize: 10 }} tickLine={false} width={140} />
                  <Tooltip
                    contentStyle={{ background: "#1a1a1a", border: "1px solid #2a2a2a", borderRadius: 8 }}
                    labelStyle={{ color: "#aaa" }}
                    formatter={(v, _n, props) => [
                      `${v}%`,
                      (props.payload as { full_name: string }).full_name,
                    ]}
                  />
                  <Bar dataKey="weight" radius={[0, 4, 4, 0]}>
                    {chartData.map((entry, i) => (
                      <Cell key={i} fill={weightColor(entry.weight)} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
              <div className="flex gap-5 text-xs text-[#888] justify-center mt-3">
                <span><span className="inline-block w-2 h-2 rounded-full bg-[#00ff88] mr-1" />≥ 3% — High conviction</span>
                <span><span className="inline-block w-2 h-2 rounded-full bg-[#ff9944] mr-1" />≥ 1% — Moderate</span>
                <span><span className="inline-block w-2 h-2 rounded-full bg-[#555] mr-1" />{'<'} 1% — Minimal</span>
              </div>
            </div>
          </section>

          {/* Fund cards */}
          <section>
            <h3 className="text-base font-semibold mb-4">All {selected.total_funds} Funds Holding {selected.display_name}</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {selected.funds.map((f) => {
                const color = weightColor(f.weight);
                return (
                  <div
                    key={f.scheme_name}
                    className="bg-[#111] border border-[#2a2a2a] rounded-xl p-4 border-l-[3px]"
                    style={{ borderLeftColor: color }}
                  >
                    <p className="text-[#888] text-xs mb-1">{f.fund_house}</p>
                    <p className="font-medium text-sm mb-3">{f.scheme_name}</p>
                    <div className="flex items-center justify-between">
                      <span className="text-[#888] text-sm">Portfolio Weight</span>
                      <span className="font-bold" style={{ color }}>{f.weight}%</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        </div>
      )}

      {!selected && !detailLoading && !query.trim() && (
        <div className="text-center py-20 text-[#555]">
          <Search size={40} className="mx-auto mb-4 opacity-20" />
          <p>Search for a stock to see which funds hold it</p>
          <div className="flex gap-2 justify-center mt-4 flex-wrap">
            {["HDFC Bank", "Infosys", "Reliance", "TCS", "ICICI Bank"].map((s) => (
              <button
                key={s}
                onClick={() => { setQuery(s); inputRef.current?.focus(); }}
                className="text-xs px-3 py-1.5 border border-[#2a2a2a] rounded-full text-[#888] hover:text-white hover:border-[#444] transition-colors"
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
