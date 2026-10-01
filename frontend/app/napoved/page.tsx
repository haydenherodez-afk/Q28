"use client";

import { useYear } from "@/components/AppShell";
import { MonthBars } from "@/components/charts";
import { Alert, ErrorBox, PageHeader, Section, Spinner, useApi } from "@/components/ui";
import { MONTHS, eur, toNum } from "@/lib/fmt";

type Scenario = { key: string; label: string; how: string; revenue: string; expenses: string; prispevki: string; dohodnina: string; drzavi_skupaj: string; neto: string; akontacija_naslednje_leto: string; scheme: string; warnings: string[] };
type F = { revenue_ytd: string; elapsed_months: string; remaining_months: string; monthly: { month: number; revenue: string }[]; avg_month: string; trend_per_month: string; scenarios: Scenario[]; note: string };

export default function Napoved() {
  const { year } = useYear();
  const f = useApi<F>(`/forecast?year=${year}`);
  const d = f.data;
  return (
    <div>
      <PageHeader title="🔮 Forecast" subtitle="Napoved prihodkov do konca leta in davki za vsak scenarij (izračun z istim davčnim enginom)." />
      <ErrorBox error={f.error} />
      {!d ? <Spinner /> : (
        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {d.scenarios.map((s) => (
              <div key={s.key} className={`card p-4 ${s.key === "CURRENT" ? "ring-2 ring-accent" : ""}`}>
                <div className="text-xs font-semibold uppercase tracking-wide text-ink-2">{s.key} · {s.label}</div>
                <div className="num mt-1 text-2xl font-extrabold">{eur(s.revenue)}</div>
                <div className="mt-1 text-xs text-ink-3">{s.how}</div>
              </div>
            ))}
          </div>
          <div className="grid gap-5 lg:grid-cols-2">
            <Section title={`Prihodki po mesecih ${year}`}>
              <MonthBars data={d.monthly.map((m) => ({ label: MONTHS[m.month - 1], value: toNum(m.revenue) }))} />
              <p className="mt-2 text-xs text-ink-3">Povprečje {eur(d.avg_month)}/mesec · trend {eur(d.trend_per_month)}/mesec · pretečeno {d.elapsed_months} mes., preostane {d.remaining_months} mes.</p>
            </Section>
            <Section title="Obveznosti po scenarijih">
              <div className="-mx-2 overflow-x-auto">
                <table className="tbl">
                  <thead><tr><th>Scenarij</th><th className="r">Prihodki</th><th className="r">Prispevki</th><th className="r">Dohodnina</th><th className="r">Ostane</th><th className="r">Akont. {year + 1}</th></tr></thead>
                  <tbody>
                    {d.scenarios.map((s) => (
                      <tr key={s.key}>
                        <td className="font-medium">{s.label}</td>
                        <td className="r">{eur(s.revenue)}</td>
                        <td className="r">{eur(s.prispevki)}</td>
                        <td className="r">{eur(s.dohodnina)}</td>
                        <td className="r font-semibold">{eur(s.neto)}</td>
                        <td className="r">{eur(s.akontacija_naslednje_leto)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Section>
          </div>
          {Array.from(new Set(d.scenarios.flatMap((s) => s.warnings))).map((w) => <Alert key={w} kind="warning">{w}</Alert>)}
          <p className="text-xs text-ink-3">{d.note}</p>
        </div>
      )}
    </div>
  );
}
