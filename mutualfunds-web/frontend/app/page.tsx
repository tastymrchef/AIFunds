"use client";

import { useEffect, useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { MetricCard } from "@/components/MetricCard";
import { Spinner } from "@/components/Spinner";
import { Search, ExternalLink } from "lucide-react";

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

interface MarketHealthWindow {
  score: number;
  label: "Bullish" | "Bearish" | "Neutral";
  color: string;
  nifty_pct: number;
  sensex_pct: number;
  gold_pct: number;
  silver_pct: number;
}

interface MarketHealth {
  score: number;
  label: "Bullish" | "Bearish" | "Neutral";
  color: string;
  summary: string;
  today: MarketHealthWindow;
  two_week: MarketHealthWindow;
}

interface NewsItem {
  title: string;
  source: string;
  url: string;
  timestamp: number;
  time_ago: string;
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function HomePage() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<{ scheme_code: string; scheme_name: string }[]>([]);
  const [pulse, setPulse] = useState<PulseData | null>(null);
  const [health, setHealth] = useState<MarketHealth | null>(null);
  const [news, setNews] = useState<NewsItem[]>([]);
  const [newsLoading, setNewsLoading] = useState(true);
  const [topPerformers, setTopPerformers] = useState<TopPerformers | null>(null);
  const [tpDate, setTpDate] = useState<string>("");
  const debounceRef = useRef<NodeJS.Timeout | null>(null);

  // Load market pulse + health in parallel
  useEffect(() => {
    fetch("/api/market/pulse")
      .then((r) => r.json())
      .then(setPulse)
      .catch(console.error);

    fetch("/api/market/health")
      .then((r) => r.json())
      .then(setHealth)
      .catch(console.error);

    fetch("/api/market/news")
      .then((r) => r.json())
      .then((d) => setNews(d.news ?? []))
      .catch(console.error)
      .finally(() => setNewsLoading(false));
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

      {/* Market Health — Today vs 2-Week */}
      {health && (
        <section>
          <div className="flex items-baseline gap-3 mb-4">
            <h2 className="text-xl font-semibold">Market Mood</h2>
            {/* Overall badge driven by 2-week score */}
            <span className="text-sm font-semibold px-2 py-0.5 rounded-full" style={{ color: health.color, background: health.color + "22" }}>
              {health.label}
            </span>
          </div>
          <p className="text-[#888] text-sm mb-4">{health.summary}</p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Today card */}
            {(["today", "two_week"] as const).map((key) => {
              const w = health[key];
              const isToday = key === "today";
              const title = isToday ? "Today" : "Last 2 Weeks";
              const rows: [string, number][] = [
                ["Nifty 50",  w.nifty_pct],
                ["Sensex",    w.sensex_pct],
                ["Gold",      w.gold_pct],
                ["Silver",    w.silver_pct],
              ];
              return (
                <div key={key} className="bg-[#111] border rounded-xl p-4 space-y-3" style={{ borderColor: w.color + "44" }}>
                  {/* Header */}
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-semibold text-[#aaa]">{title}</p>
                    <div className="flex items-center gap-2">
                      <div className="w-10 h-10 rounded-full flex flex-col items-center justify-center border-2 shrink-0" style={{ borderColor: w.color }}>
                        <span className="text-xs font-bold leading-none" style={{ color: w.color }}>{w.score}</span>
                        <span className="text-[9px] text-[#666] leading-none">/ 100</span>
                      </div>
                      <span className="text-sm font-bold" style={{ color: w.color }}>{w.label}</span>
                    </div>
                  </div>
                  {/* Index rows */}
                  <div className="space-y-2">
                    {rows.map(([label, val]) => {
                      const pos = val >= 0;
                      const c = pos ? "#00ff88" : "#ff4444";
                      const barW = Math.min(Math.abs(val) * 10, 100);   // 10% move = full bar
                      return (
                        <div key={label} className="flex items-center gap-3">
                          <span className="text-xs text-[#666] w-16 shrink-0">{label}</span>
                          <div className="flex-1 h-1.5 bg-[#222] rounded-full overflow-hidden">
                            <div className="h-full rounded-full" style={{ width: `${barW}%`, background: c }} />
                          </div>
                          <span className="text-xs font-medium w-14 text-right" style={{ color: c }}>
                            {pos ? "+" : ""}{val}%
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* Market News */}
      <section>
        <h2 className="text-xl font-semibold mb-4">📰 Market News</h2>
        {newsLoading ? (
          <div className="flex gap-3 items-center text-[#888]"><Spinner /> Loading news...</div>
        ) : news.length === 0 ? (
          <p className="text-[#555] text-sm">No news available right now.</p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {news.map((item, i) => (
              <a
                key={i}
                href={item.url || "#"}
                target="_blank"
                rel="noopener noreferrer"
                className="bg-[#111] border border-[#2a2a2a] hover:border-[#444] rounded-xl p-4 flex flex-col gap-2 transition-colors group"
              >
                <p className="text-sm text-white leading-snug group-hover:text-[#00ff88] transition-colors line-clamp-2">
                  {item.title}
                </p>
                <div className="flex items-center justify-between mt-auto">
                  <span className="text-xs text-[#555]">{item.source} · {item.time_ago}</span>
                  {item.url && <ExternalLink size={12} className="text-[#444] group-hover:text-[#888] transition-colors" />}
                </div>
              </a>
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

    </div>
  );
}