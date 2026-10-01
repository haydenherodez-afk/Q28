"use client";

import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { eur, eur0 } from "@/lib/fmt";

const axis = { stroke: "var(--ink-3)", fontSize: 12, tickLine: false, axisLine: { stroke: "var(--grid)" } } as const;
const tooltipStyle = {
  contentStyle: { background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12, color: "var(--ink)", fontSize: 13 },
  labelStyle: { color: "var(--ink)", fontWeight: 600 },
  itemStyle: { color: "var(--ink)" },
  cursor: { fill: "var(--surface-2)" },
};
const k = (v: number) => `${Math.round(v / 1000)}k`;

export type StackSeries = { key: string; label: string; color: string };

/** Prihodek -> obveznosti -> neto, naložen stolpec po prihodkovnem nivoju. */
export function StackedBars({ data, series, x }: { data: Record<string, number | string>[]; series: StackSeries[]; x: string }) {
  return (
    <div className="h-72 w-full">
      <ResponsiveContainer>
        <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }} barCategoryGap="28%">
          <CartesianGrid vertical={false} stroke="var(--grid)" />
          <XAxis dataKey={x} {...axis} tickFormatter={(v) => eur0(v)} />
          <YAxis {...axis} tickFormatter={k} width={44} />
          <Tooltip {...tooltipStyle} formatter={(v) => eur(Number(v))} labelFormatter={(l) => `Prihodki ${eur0(Number(l))}`} />
          <Legend wrapperStyle={{ fontSize: 12 }} iconType="circle" formatter={(v) => <span style={{ color: "var(--ink-2)" }}>{v}</span>} />
          {series.map((s, i) => (
            <Bar key={s.key} dataKey={s.key} name={s.label} stackId="a" fill={s.color} stroke="var(--surface)" strokeWidth={2}
              radius={i === series.length - 1 ? [4, 4, 0, 0] : [0, 0, 0, 0]} maxBarSize={56} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function Lines({ data, series, x }: { data: Record<string, number | string>[]; series: StackSeries[]; x: string }) {
  return (
    <div className="h-64 w-full">
      <ResponsiveContainer>
        <LineChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke="var(--grid)" />
          <XAxis dataKey={x} {...axis} tickFormatter={(v) => eur0(v)} />
          <YAxis {...axis} tickFormatter={k} width={44} />
          <Tooltip {...tooltipStyle} cursor={{ stroke: "var(--ink-3)" }} formatter={(v) => eur(Number(v))} labelFormatter={(l) => `Prihodki ${eur0(Number(l))}`} />
          <Legend wrapperStyle={{ fontSize: 12 }} iconType="circle" formatter={(v) => <span style={{ color: "var(--ink-2)" }}>{v}</span>} />
          {series.map((s) => (
            <Line key={s.key} type="monotone" dataKey={s.key} name={s.label} stroke={s.color} strokeWidth={2}
              dot={{ r: 4, strokeWidth: 2, stroke: "var(--surface)", fill: s.color }} activeDot={{ r: 6 }} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function MonthBars({ data }: { data: { label: string; value: number }[] }) {
  return (
    <div className="h-60 w-full">
      <ResponsiveContainer>
        <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke="var(--grid)" />
          <XAxis dataKey="label" {...axis} />
          <YAxis {...axis} tickFormatter={k} width={44} />
          <Tooltip {...tooltipStyle} formatter={(v) => [eur(Number(v)), "Prihodki"]} />
          <Bar dataKey="value" name="Prihodki" fill="var(--series-1)" radius={[4, 4, 0, 0]} maxBarSize={36} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
