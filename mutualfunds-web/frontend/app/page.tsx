"use client";

import { useEffect, useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { MetricCard } from "@/components/MetricCard";
import { Spinner } from "@/components/Spinner";
import { Search } from "lucide-react";

// ── Types ────────────────────────────────────────────────────────────────────

interface PulseData {
  [key: string]: { current: number; change: number; change_pct: number };
}

interface TopFund {
  name: string;
  return_1y: number | null;
  return_6m: number | null;
}

interface TopPerformers {
  [sector: string]: TopFund[];
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function HomePage() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<{ scheme_code: string; scheme_name: string }[]>([]);
  const [pulse, setPulse] = useState<PulseData | null>(null);
  const [topPerformers, setTopPerformers] = useState<TopPerformers | null>(null);
  const [tpDate, setTpDate] = useState<string>("");
  const debounceRef = useRef<NodeJS.Timeout | null>(null);

  // Load market pulse
  useEffect(() => {
    fetch("/api/market/pulse")
      .then((r) => r.json())
      .then(setPulse)
      .catch(console.error);
  }, []);

  // Load top performers
  useEffect(() => {
    fetch("/api/market/top-performers")
      .then((r) => r.json())
      .then((d) => {
        setTopPerformers(d.data);
        setTpDate(d.generated_at ?? "");
      })
      .catch(console.error);
  }, []);

  // Debounced search suggestions
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (query.length < 2) { setSuggestions([]); return; }
    debounceRef.current = setTimeout(() => {
      fetch(`/api/funds/search?q=${encodeURIComponent(query)}`)
        .then((r) => r.json())
        .then((d) => setSuggestions(d.results ?? []))
        .catch(console.error);
    }, 300);
  }, [query]);

  function handleSelect(code: string) {
    setSuggestions([]);
    setQuery("");
    router.push(`/funds/${code}`);
  }

  return (
    <div className="space-y-10">
      {/* Hero */}
      <div className="text-center pt-8 pb-4">
        <h1 className="text-4xl font-bold mb-2">📈 MutualFund AI</h1>
        <p className="text-[#888] text-lg">Your intelligent guide to Indian mutual funds</p>
      </div>

      {/* Search */}
      <div className="relative max-w-2xl mx-auto">
        <div className="flex items-center bg-[#111] border border-[#2a2a2a] rounded-xl px-4 py-3 gap-3 focus-within:border-[#00ff88] transition-colors">
          <Search size={18} className="text-[#555]" />
          <input
            className="flex-1 bg-transparent outline-none text-white placeholder-[#555]"
            placeholder="Search any mutual fund — e.g. Parag Parikh Flexi Cap, HDFC Small Cap..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && suggestions.length > 0) handleSelect(suggestions[0].scheme_code);
            }}
          />
        </div>

        {/* Dropdown */}
        {suggestions.length > 0 && (
          <div className="absolute top-full mt-1 w-full bg-[#111] border border-[#2a2a2a] rounded-xl overflow-hidden z-50 shadow-xl">
            {suggestions.map((s) => (
              <button
                key={s.scheme_code}
                onClick={() => handleSelect(s.scheme_code)}
                className="w-full text-left px-4 py-3 text-sm hover:bg-[#1a1a1a] transition-colors border-b border-[#2a2a2a] last:border-0"
              >
                {s.scheme_name}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Market Pulse */}
      <section>
        <h2 className="text-xl font-semibold mb-4">Market Pulse</h2>
        {!pulse ? (
          <div className="flex gap-3 items-center text-[#888]"><Spinner /> Fetching live market data...</div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {Object.entries(pulse).map(([name, data]) => (
              "current" in data ? (
                <MetricCard
                  key={name}
                  label={name}
                  value={data.current.toLocaleString("en-IN")}
                  change={data.change}
                  changePct={data.change_pct}
                />
              ) : null
            ))}
          </div>
        )}
      </section>

      {/* Top Performers */}
      <section>
        <div className="flex items-baseline justify-between mb-4">
          <h2 className="text-xl font-semibold">🏆 Top Performers by Sector</h2>
          {tpDate && <span className="text-[#555] text-xs">Based on 1Y returns · Updated: {tpDate}</span>}
        </div>

        {!topPerformers ? (
          <div className="flex gap-3 items-center text-[#888]"><Spinner /> Loading...</div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {Object.entries(topPerformers).map(([sector, funds]) => (
              <div key={sector}>
                <p className="text-sm font-semibold text-[#888] mb-3 uppercase tracking-wider">{sector}</p>
                <div className="space-y-2">
                  {funds.map((fund) => {
                    const color = fund.return_1y && fund.return_1y > 0 ? "#00ff88" : "#ff4444";
                    const shortName = fund.name.length > 45 ? fund.name.slice(0, 45) + "…" : fund.name;
                    return (
                      <div
                        key={fund.name}
                        className="bg-[#111] rounded-lg px-4 py-3 border-l-[3px]"
                        style={{ borderLeftColor: color }}
                      >
                        <p className="text-[#aaa] text-xs mb-1">{shortName}</p>
                        <div className="flex gap-4">
                          <span className="font-bold text-sm" style={{ color }}>
                            1Y: {fund.return_1y}%
                          </span>
                          <span className="text-[#888] text-sm">6M: {fund.return_6m}%</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* CTAs */}
      <section className="grid grid-cols-1 md:grid-cols-2 gap-4 pb-8">
        <button
          onClick={() => router.push("/funds")}
          className="bg-[#111] border border-[#2a2a2a] hover:border-[#00ff88] rounded-xl p-5 text-left transition-colors group"
        >
          <p className="text-lg font-semibold group-hover:text-[#00ff88] transition-colors">🔍 Search Funds</p>
          <p className="text-[#888] text-sm mt-1">Analyse any Indian mutual fund with AI</p>
        </button>
        <button
          onClick={() => router.push("/stocks")}
          className="bg-[#111] border border-[#2a2a2a] hover:border-[#4da6ff] rounded-xl p-5 text-left transition-colors group"
        >
          <p className="text-lg font-semibold group-hover:text-[#4da6ff] transition-colors">📦 Find by Stock</p>
          <p className="text-[#888] text-sm mt-1">See which funds hold Zomato, HDFC Bank, or any stock</p>
        </button>
      </section>
    </div>
  );
}