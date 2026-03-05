"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { Search } from "lucide-react";
import { Spinner } from "@/components/Spinner";

interface FundResult {
  scheme_code: string;
  scheme_name: string;
  fund_house: string;
  scheme_category: string;
}

export default function FundsPage() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<FundResult[]>([]);
  const [loading, setLoading] = useState(false);
  const router = useRouter();
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      return;
    }
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      setLoading(true);
      fetch(`/api/funds/search?q=${encodeURIComponent(query)}`)
        .then((r) => r.json())
        .then((d) => setResults(d.results ?? []))
        .catch(console.error)
        .finally(() => setLoading(false));
    }, 300);
  }, [query]);

  function navigate(code: string) {
    router.push(`/funds/${code}`);
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6 pt-4">
      <h1 className="text-2xl font-bold">Search Funds</h1>
      <p className="text-[#888]">Search across thousands of mutual funds by name or fund house</p>

      {/* Search bar */}
      <div className="flex items-center gap-3 bg-[#111] border border-[#2a2a2a] rounded-xl px-4 py-3">
        <Search size={18} className="text-[#555]" />
        <input
          autoFocus
          className="flex-1 bg-transparent outline-none text-white placeholder-[#555]"
          placeholder="e.g. Mirae Asset ELSS, Parag Parikh Flexi Cap..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        {loading && <Spinner size={16} />}
      </div>

      {/* Results */}
      {results.length > 0 && (
        <div className="space-y-2">
          {results.map((f) => (
            <button
              key={f.scheme_code}
              onClick={() => navigate(f.scheme_code)}
              className="w-full text-left bg-[#111] border border-[#2a2a2a] rounded-xl px-4 py-3 hover:border-[#444] transition-colors group"
            >
              <div className="flex justify-between items-start">
                <div>
                  <p className="font-medium group-hover:text-[#00ff88] transition-colors">{f.scheme_name}</p>
                  <p className="text-[#888] text-sm mt-0.5">{f.fund_house}</p>
                </div>
                <span className="text-xs text-[#555] bg-[#1a1a1a] rounded-md px-2 py-1 ml-3 shrink-0">
                  {f.scheme_category}
                </span>
              </div>
            </button>
          ))}
        </div>
      )}

      {!loading && query.trim() && results.length === 0 && (
        <p className="text-[#555] text-center py-10">No funds found for "{query}"</p>
      )}

      {!query.trim() && (
        <div className="text-center py-16 text-[#555]">
          <Search size={36} className="mx-auto mb-4 opacity-20" />
          <p>Start typing to search for a fund</p>
        </div>
      )}
    </div>
  );
}
