"use client";

import Link from "next/link";
import { useYear } from "@/components/AppShell";
import { ExplainButton } from "@/components/Explain";
import { Alert, Empty, ErrorBox, PageHeader, ProgressBar, Section, Spinner, useApi } from "@/components/ui";
import { api } from "@/lib/api";
import { dateSl, eur, eur0, inDays, lateDays, pct } from "@/lib/fmt";
import type { CalItem, Dashboard } from "@/lib/types";
import { useState } from "react";

export default function Home() {
  const { year } = useYear();
  const dash = useApi<Dashboard>(`/dashboard?year=${year}`);
  const cal = useApi<{ next: CalItem[]; balance: string | null }>(`/calendar?year=${year}`);
  const [running, setRunning] = useState(false);
  const d = dash.data;

  async function runDaily() {
    setRunning(true);
    try { await api("/daily/run", { method: "POST" }); dash.reload(); } finally { setRunning(false); }
  }

  return (
    <div>
      <PageHeader
        title={d ? d.business_name : "Home"}
        subtitle={d && <>Stanje na {dateSl(d.as_of)} · {d.regime === "normiran" ? "normiranec" : "dejanski stroški"}{d.regime === "normiran" && ` (${d.scheme === "full" ? "polna shema" : "shema < 9 mesecev"})`} · pravila preverjena {dateSl(d.rules_checked_on)}</>}
        actions={<Link href="/ai" className="btn btn-primary">🤖 Vprašaj AI</Link>}
      />
      {dash.error && (dash.error.includes("ne obstaja") || dash.error.includes("ni davčnih pravil")) ? (
        <Alert kind="info">Za leto {year} v HericR ni vseh davčnih pravil (obračun je že oddan). Račune, stroške in dokumente tega leta vidiš v ustreznih razdelkih; za izračune izberi leto 2026.</Alert>
      ) : <ErrorBox error={dash.error} />}
      {dash.loading && !d && <Spinner />}
      {d && (
        <div className="space-y-5">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {d.cards.map((c) => (
              <div key={c.key} className="card p-4 sm:p-5">
                <div className="flex items-center gap-2 text-sm font-medium text-ink-2">
                  <span aria-hidden className="text-lg">{c.icon}</span>{c.label.toUpperCase()}
                </div>
                <div className={`num mt-1 text-3xl font-extrabold tracking-tight ${c.key === "se_dolgujes" && Number(c.value) > 0 ? "text-warn" : ""}`}>
                  {eur(c.value)}
                </div>
                <div className="mt-2"><ExplainButton e={c} /></div>
              </div>
            ))}
          </div>

          <div className="grid gap-5 lg:grid-cols-5">
            <Section title={`📈 Letos (${year})`} className="lg:col-span-3">
              <div className="space-y-4">
                {d.progress.map((p) => (
                  <div key={p.key}>
                    <div className="mb-1 flex flex-wrap items-baseline justify-between gap-2 text-sm">
                      <span className="font-medium">{p.label}</span>
                      <span className="num text-ink-2">
                        {p.max ? <>{eur0(p.value)} / {eur0(p.max)} · {pct(p.ratio ?? 0)}</> : p.note}
                      </span>
                    </div>
                    {p.ratio !== null && <ProgressBar ratio={p.ratio} tone={(p.ratio ?? 0) > 1 ? "bad" : (p.ratio ?? 0) > 0.85 && p.key !== "goal" ? "warn" : "accent"} />}
                    {p.note && p.max && <div className="mt-1 text-xs text-ink-3">{p.note}</div>}
                  </div>
                ))}
              </div>
            </Section>

            <Section title="📅 Naslednji roki" className="lg:col-span-2" actions={<Link href="/koledar" className="text-sm text-accent">vsi →</Link>}>
              {cal.loading && !cal.data ? <Spinner /> : cal.data?.next.length ? (
                <ul className="space-y-2">
                  {cal.data.next.slice(0, 4).map((i) => (
                    <li key={i.kind + i.period} className="flex items-start justify-between gap-3 rounded-xl bg-surface-2 px-3 py-2">
                      <div className="min-w-0">
                        <div className="text-sm font-medium">{i.title}</div>
                        <div className="text-xs text-ink-2">
                          {i.days_until < 0 ? <span className="font-semibold text-bad">zamujeno {lateDays(-i.days_until)}</span>
                            : i.days_until === 0 ? <span className="font-semibold text-warn">danes</span>
                            : <>{inDays(i.days_until)}</>} · {dateSl(i.due_date)}
                        </div>
                        {i.cash_warning && <div className="mt-1 text-xs text-warn">⚠️ {i.cash_warning}</div>}
                      </div>
                      <div className="num shrink-0 text-sm font-semibold">{i.amount ? eur(i.amount) : "—"}{i.estimated && <span className="text-ink-3">*</span>}</div>
                    </li>
                  ))}
                </ul>
              ) : <Empty>Ni odprtih rokov.</Empty>}
            </Section>
          </div>

          <div className="grid gap-5 lg:grid-cols-2">
            <Section title={<>⚠️ {d.attention.length} {d.attention.length === 1 ? "stvar zahteva" : d.attention.length === 2 ? "stvari zahtevata" : "stvari zahtevajo"} tvojo pozornost</>}
              actions={<Link href="/napake" className="text-sm text-accent">preglej →</Link>}>
              {d.attention.length === 0 ? <Alert kind="good">Vse je v redu — ni napak ali opozoril.</Alert> : (
                <ul className="space-y-2.5">
                  {d.attention.slice(0, 6).map((a) => (
                    <li key={a.key} className="flex items-start gap-2 text-sm">
                      <span aria-hidden className="mt-0.5">{a.severity === "error" ? "⛔" : "⚠️"}</span>
                      <span className="min-w-0"><span className="font-medium">{a.title}</span><span className="block text-xs text-ink-2">{a.detail}</span></span>
                    </li>
                  ))}
                  {d.attention.length > 6 && <li className="text-xs text-ink-3">… in še {d.attention.length - 6}</li>}
                </ul>
              )}
              {d.attention_minor > 0 && <p className="mt-3 text-xs text-ink-3">+ {d.attention_minor} manjših opomb (npr. manjkajoči dokumenti) v razdelku Napake.</p>}
            </Section>

            <Section title="🤖 Današnji pregled" actions={<button className="btn text-xs" onClick={runDaily} disabled={running}>{running ? "…" : "Osveži"}</button>}>
              {d.daily_report ? (
                <div className="space-y-2 text-sm">
                  <div className="text-xs text-ink-3">{dateSl(d.daily_report.day)}</div>
                  {d.daily_report.ai_text ? <p className="whitespace-pre-line">{d.daily_report.ai_text}</p> : (
                    <dl className="grid grid-cols-2 gap-x-4 gap-y-1">
                      {([
                        ["Prihodki ta mesec", "prihodki_ta_mesec"], ["Napoved letos", "napoved_letos_trenutni_tempo"],
                        ["Predvidena dohodnina", "predvidena_dohodnina_letos"], ["Akontacija (letno)", "akontacija_odmerjena_letno"],
                        ["Razlika do končne", "razlika_dohodnina_vs_akontacija"], ["Davčna rezerva", "davcna_rezerva"],
                      ] as const).map(([l, k]) => (
                        <div key={k} className="contents">
                          <dt className="text-ink-2">{l}</dt>
                          <dd className="num text-right font-medium">{eur(d.daily_report!.data[k] as string)}</dd>
                        </div>
                      ))}
                    </dl>
                  )}
                </div>
              ) : <Empty>Pregled se pripravi vsak dan ob 7:00. Klikni "Osveži" za takojšen pregled.</Empty>}
            </Section>
          </div>

          {d.warnings.length > 0 && (
            <div className="space-y-2">{d.warnings.map((w, i) => <Alert key={i} kind="warning">{w}</Alert>)}</div>
          )}
        </div>
      )}
    </div>
  );
}
