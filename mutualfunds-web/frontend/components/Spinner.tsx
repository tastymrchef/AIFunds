export function Spinner({ size = 20 }: { size?: number }) {
  return (
    <div
      className="animate-spin rounded-full border-2 border-[#2a2a2a] border-t-[#00ff88]"
      style={{ width: size, height: size }}
    />
  );
}
