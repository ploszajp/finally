"use client";

import { useEffect, useRef } from "react";
import {
  AreaSeries,
  ColorType,
  CrosshairMode,
  LineStyle,
  createChart,
  type IChartApi,
  type IPriceLine,
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

const AUTO_FIT_POINTS = 120;

const hexToRgba =(hex: string, alpha: number) => {
  const n = parseInt(hex.replace("#", ""), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
};

const seriesColors = (color: string) => ({
  lineColor: color,
  topColor: hexToRgba(color, 0.28),
  bottomColor: hexToRgba(color, 0.02),
  priceLineColor: color,
});

/**
 * Canvas area chart (Lightweight Charts v5) that fills its parent. The chart is
 * created once per mount; prop changes are applied with applyOptions/setData.
 */
export default function TimeSeriesChart({ data, color, secondsVisible = true, baseline = null }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Area"> | null>(null);
  const baselineRef = useRef<IPriceLine | null>(null);
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
      timeScale: { borderColor: "#232d3a", timeVisible: true },
      crosshair: { mode: CrosshairMode.Magnet },
    });
    seriesRef.current = chart.addSeries(AreaSeries, {
      lineWidth: 2,
      priceLineVisible: true,
      priceLineStyle: LineStyle.Dotted,
    });
    chartRef.current = chart;
    lastLengthRef.current = 0;
    return () => {
      seriesRef.current = null;
      baselineRef.current = null;
      chartRef.current = null;
      chart.remove();
    };
  }, []);

  useEffect(() => {
    seriesRef.current?.applyOptions(seriesColors(color));
  }, [color]);

  useEffect(() => {
    chartRef.current?.applyOptions({ timeScale: { secondsVisible } });
  }, [secondsVisible]);

  useEffect(() => {
    const series = seriesRef.current;
    if (!series) return;
    series.setData(data.map((p) => ({ time: p.time as UTCTimestamp, value: p.value })));
    // Keep fitting while the series is short (it fills in from page load), and
    // whenever it is replaced by a shorter one; after that the user can zoom/pan.
    if (data.length > 0 && (data.length <= AUTO_FIT_POINTS || data.length < lastLengthRef.current)) {
      chartRef.current?.timeScale().fitContent();
    }
    lastLengthRef.current = data.length;
  }, [data]);

  useEffect(() => {
    const series = seriesRef.current;
    if (!series) return;
    if (baselineRef.current) {
      series.removePriceLine(baselineRef.current);
      baselineRef.current = null;
    }
    if (baseline != null) {
      baselineRef.current = series.createPriceLine({
        price: baseline,
        color: "#4f5b6b",
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: false,
      });
    }
  }, [baseline]);

  return <div ref={containerRef} className="h-full w-full" />;
}
