interface FitScoreGaugeProps { score: number; }

function getTier(score: number) {
  if (score >= 75) return { label: "Strong Match",   color: "#10b981", bg: "#d1fae5" };
  if (score >= 50) return { label: "Moderate Match", color: "#f59e0b", bg: "#fef3c7" };
  return              { label: "Needs Work",        color: "#ef4444", bg: "#fee2e2" };
}

function arcPath(cx: number, cy: number, r: number, startDeg: number, endDeg: number) {
  const rad = (d: number) => (d * Math.PI) / 180;
  const x1 = cx + r * Math.cos(rad(startDeg)), y1 = cy + r * Math.sin(rad(startDeg));
  const x2 = cx + r * Math.cos(rad(endDeg)),   y2 = cy + r * Math.sin(rad(endDeg));
  const large = endDeg - startDeg > 180 ? 1 : 0;
  return `M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2}`;
}

export default function FitScoreGauge({ score }: FitScoreGaugeProps) {
  const clamped = Math.max(0, Math.min(100, score));
  const tier = getTier(clamped);
  const size = 200;
  const cx = size / 2;
  const cy = size / 2 + 10;
  const r = 80;
  const sw = 16;
  const START = 200;
  const END = 340;
  const SWEEP = 140;
  const bgPath   = arcPath(cx, cy, r, START, END);
  const fillEnd  = START + SWEEP * (clamped / 100);
  const fillPath = clamped > 0 ? arcPath(cx, cy, r, START, fillEnd) : "";

  return (
    <div className="flex flex-col items-center gap-1">
      <svg
        width={size}
        height={size - 24}
        viewBox={`0 0 ${size} ${size - 24}`}
        aria-label={`Fit score: ${clamped}%`}
        role="img"
      >
        {/* Track */}
        <path d={bgPath} fill="none" stroke="#f3f4f6" strokeWidth={sw} strokeLinecap="round" />
        {/* Fill */}
        {fillPath && (
          <path
            d={fillPath}
            fill="none"
            stroke={tier.color}
            strokeWidth={sw}
            strokeLinecap="round"
            style={{ transition: "stroke-dasharray 0.8s ease" }}
          />
        )}
        {/* Score number */}
        <text
          x={cx}
          y={cy + 8}
          textAnchor="middle"
          dominantBaseline="middle"
          fontSize="44"
          fontWeight="800"
          fill={tier.color}
          fontFamily="Inter, system-ui, sans-serif"
        >
          {clamped}
        </text>
        {/* Percent sign */}
        <text
          x={cx + 30}
          y={cy - 8}
          textAnchor="middle"
          dominantBaseline="middle"
          fontSize="16"
          fontWeight="600"
          fill={tier.color}
          opacity="0.7"
        >
          %
        </text>
      </svg>
      {/* Label pill */}
      <span
        className="rounded-full px-3 py-0.5 text-xs font-semibold tracking-wide"
        style={{ background: tier.bg, color: tier.color }}
      >
        {tier.label}
      </span>
    </div>
  );
}
