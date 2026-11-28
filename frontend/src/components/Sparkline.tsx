import type { PricePoint } from "@/lib/types";

interface Props {
  points: PricePoint[];
  width?: number;
  height?: number;
  testId?: string;
}

/** Tiny SVG line of the prices received since page load. */
export default function Sparkline({ points, width = 72, height = 22, testId }: Props) {
  if (points.length < 2) {
    return (
      <svg data-testid={testId} width={width} height={height} aria-hidden>
        <line
          x1={0}
          x2={width}
          y1={height / 2}
          y2={height / 2}
          stroke="var(--color-line-strong)"
          strokeDasharray="2 3"
        />
      </svg>
    );
  }
  const values = points.map((p) => p.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const step = width / (points.length - 1);
  const d = values
    .map((v, i) => `${(i * step).toFixed(1)},${(height - 2 - ((v - min) / span) * (height - 4)).toFixed(1)}`)
    .join(" ");
  const rising = values[values.length - 1] >= values[0];
  return (
    <svg data-testid={testId} width={width} height={height} aria-hidden>
      <polyline
        points={d}
        fill="none"
        stroke={rising ? "var(--color-up)" : "var(--color-down)"}
        strokeWidth={1.25}
        strokeLinejoin="round"
      />
    </svg>
  );
}
