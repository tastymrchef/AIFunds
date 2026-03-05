import clsx from "clsx";

interface MetricCardProps {
  label: string;
  value: string;
  change: number;
  changePct: number;
}

export function MetricCard({ label, value, change, changePct }: MetricCardProps) {
  const positive = change >= 0;
  const color = positive ? "text-[#00ff88]" : "text-[#ff4444]";
  const arrow = positive ? "▲" : "▼";

  return (
    <div className="bg-[#111] border border-[#2a2a2a] rounded-xl p-4">
      <p className="text-[#888] text-xs mb-1">{label}</p>
      <p className="text-white text-xl font-bold">{value}</p>
      <p className={clsx("text-sm mt-1", color)}>
        {arrow} {Math.abs(change).toLocaleString()} ({Math.abs(changePct).toFixed(2)}%)
      </p>
    </div>
  );
}
