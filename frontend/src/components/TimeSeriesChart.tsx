"use client";

import { useEffect, useRef } from "react";
import {
  AreaSeries,
  ColorType,
  CrosshairMode,
  LineStyle,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";
import type { PricePoint } from "@/lib/types";

interface Props {
  data: PricePoint[];
  color: string;
  /** Show seconds on the time axis (live price chart) or not (P&L history). */
  secondsVisible?: boolean;
  /** Optional horizontal reference line (e.g. starting value). */
  baseline?: number | null;
}

const hexToRgba = (hex: string, alpha: number) => {
  const n = parseInt(hex.replace("#", ""), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
};

/** Canvas area chart (Lightweight Charts v5) that fills its parent. */
export default function TimeSeriesChart({ data, color, secondsVisible = true, baseline = null }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Area"> | null>(null);
  const lastLengthRef = useRef(0);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const chart = createChart(el, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#7c8899",
        fontFamily: "IBM Plex Mono, ui-monospace, monospace",
        fontSize: 11,
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: "rgba(35, 45, 58, 0.55)" },
        horzLines: { color: "rgba(35, 45, 58, 0.55)" },
      },
      rightPriceScale: { borderColor: "#232d3a" },
      timeScale: { borderColor: "#232d3a", timeVisible: true, secondsVisible },
      crosshair: { mode: CrosshairMode.Magnet },
    });
    const series = chart.addSeries(AreaSeries, {
      lineColor: color,
      topColor: hexToRgba(color, 0.28),
      bottomColor: hexToRgba(color, 0.02),
      lineWidth: 2,
      priceLineVisible: true,
      priceLineColor: color,
      priceLineStyle: LineStyle.Dotted,
    });
    chartRef.current = chart;
    seriesRef.current = series;
    lastLengthRef.current = 0;
    return () => {
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, [color, secondsVisible]);

  useEffect(() => {
    const series = seriesRef.current;
    if (!series) return;
    series.setData(data.map((p) => ({ time: p.time as UTCTimestamp, value: p.value })));
    // Fit once when data first arrives or is replaced by a different series.
    if (lastLengthRef.current === 0 || data.length < lastLengthRef.current) {
      chartRef.current?.timeScale().fitContent();
    }
    lastLengthRef.current = data.length;
  }, [data, color, secondsVisible]);

  useEffect(() => {
    const series = seriesRef.current;
    if (!series || baseline == null) return;
    const line = series.createPriceLine({
      price: baseline,
      color: "#4f5b6b",
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      axisLabelVisible: false,
    });
    return () => {
      // Series may already be gone if the chart was recreated.
      try {
        series.removePriceLine(line);
      } catch {
        /* chart removed */
      }
    };
  }, [baseline, color, secondsVisible]);

  return <div ref={containerRef} className="h-full w-full" />;
}
