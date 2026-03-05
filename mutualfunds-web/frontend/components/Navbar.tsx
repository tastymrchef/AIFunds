"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { TrendingUp, Search, Package } from "lucide-react";
import clsx from "clsx";

const links = [
  { href: "/",        label: "Home",           icon: TrendingUp },
  { href: "/funds",   label: "Search Funds",   icon: Search },
  { href: "/stocks",  label: "Find by Stock",  icon: Package },
];

export function Navbar() {
  const path = usePathname();

  return (
    <nav className="border-b border-[#2a2a2a] bg-[#0a0a0a] sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 h-14 flex items-center justify-between">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-2 font-bold text-lg">
          <span className="text-[#00ff88]">📈</span>
          <span>MutualFund AI</span>
        </Link>

        {/* Nav links */}
        <div className="flex items-center gap-1">
          {links.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className={clsx(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm transition-colors",
                path === href
                  ? "bg-[#1a1a1a] text-white"
                  : "text-[#888] hover:text-white hover:bg-[#1a1a1a]"
              )}
            >
              <Icon size={14} />
              {label}
            </Link>
          ))}
        </div>
      </div>
    </nav>
  );
}
