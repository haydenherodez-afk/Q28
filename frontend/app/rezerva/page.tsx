"use client";

import { useYear } from "@/components/AppShell";
import { ExplainButton } from "@/components/Explain";
import { Alert, Badge, Empty, ErrorBox, PageHeader, Section, Spinner, useApi } from "@/components/ui";
import { dateSl, eur } from "@/lib/fmt";
import type { Explained } from "@/lib/types";

type R = { balance: string | null; balance_date: string | null; components: Record<string, string>; reserve: Explained; available?: Explained; available_after_buffer?: string; safety_buffer: string; warning?: string };
type C = { accounting: Explained; cash: Explained; unpaid_total: string; bank_inflow: string; bank_outflow: string; balance: string | null; open_invoices: { id: number; number: string; customer: string; due_date: string | null; open: string; days_overdue: number }[]; note: string };
const LABEL: Record<string, string> = { prispevki: "prispevke", akontacija: "akontacijo", dohodnina: "dohodnino", ddv: "DDV" };

export default function Rezerva() {
  const { year } = useYear();
  const r = useApi<R>(`/reserve?year=${year}`);
  const c = useApi<C>(`/cash?year=${year}`);
  return (
    <div>
      <PageHeader title="🏦 Tax Reserve & Profit vs Cash" subtitle="Koliko denarja mora ostati na računu za državo — in koliko je res tvojega." />
      <ErrorBox error={r.error || c.error} />
      <div className="grid gap-5 lg:grid-cols-2">
        <Section title="Davčna rezerva — ne dotikaj se">
          {!r.data ? <Spinner /> : (
            <div className="space-y-1 text-sm">
              <div className="flex justify-between py-1"><span>Trenutno na TRR {r.data.balance_date && <span className="text-ink-3">({dateSl(r.data.balance_date)})</span>}</span><span className="num font-semibold">{eur(r.data.balance)}</span></div>
              <div className="pt-2 text-xs font-semibold uppercase tracking-wide text-ink-2">Rezerva za</div>
              {Object.entries(r.data.components).map(([k, v]) => (
                <div key={k} className="flex justify-between py-0.5"><span className="text-ink-2">{LABEL[k] ?? k}</span><span className="num">{eur(v)}</span></div>
              ))}
              <div className="mt-2 flex justify-between border-t border-line pt-2 text-base"><span className="font-semibold">DAVČNA REZERVA</span><span className="num font-bold">{eur(r.data.reserve.value)}</span></div>
              <ExplainButton e={r.data.reserve} />
              {r.data.available && (
                <div className="mt-3 rounded-xl bg-surface-2 p-4">
                  <div className="text-xs font-semibold uppercase tracking-wide text-ink-2">Razpoložljivo</div>
                  <div className="num text-3xl font-extrabold">{eur(r.data.available.value)}</div>
                  <div className="text-xs text-ink-3">po varnostni rezervi {eur(r.data.safety_buffer)}: <b className="num">{eur(r.data.available_after_buffer)}</b></div>
                </div>
              )}
              {r.data.warning && <div className="pt-2"><Alert kind="warning">{r.data.warning}</Alert></div>}
            </div>
          )}
        </Section>
        <Section title="📊 Profit vs Cash">
          {!c.data ? <Spinner /> : (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-xl bg-surface-2 p-4">
                  <div className="text-xs font-semibold uppercase text-ink-2">Accounting — ustvaril si</div>
                  <div className="num text-2xl font-extrabold">{eur(c.data.accounting.value)}</div>
                  <ExplainButton e={c.data.accounting} label="razlaga" />
                </div>
                <div className="rounded-xl bg-surface-2 p-4">
                  <div className="text-xs font-semibold uppercase text-ink-2">Cash — prejel si</div>
                  <div className="num text-2xl font-extrabold">{eur(c.data.cash.value)}</div>
                  <ExplainButton e={c.data.cash} label="razlaga" />
                </div>
              </div>
              <div className="text-sm">Kupci ti dolgujejo: <b className="num">{eur(c.data.unpaid_total)}</b></div>
              <Alert kind="info">{c.data.note}</Alert>
              {c.data.open_invoices.length === 0 ? <Empty>Vsi računi so plačani. 🎉</Empty> : (
                <table className="tbl">
                  <thead><tr><th>Račun</th><th>Kupec</th><th className="r">Odprto</th><th>Zamuda</th></tr></thead>
                  <tbody>{c.data.open_invoices.map((i) => (
                    <tr key={i.id}><td>{i.number}</td><td>{i.customer}</td><td className="r font-semibold">{eur(i.open)}</td>
                      <td>{i.days_overdue > 0 ? <Badge kind={i.days_overdue > 30 ? "error" : "warning"}>{i.days_overdue} dni</Badge> : <span className="text-xs text-ink-3">rok {dateSl(i.due_date)}</span>}</td></tr>
                  ))}</tbody>
                </table>
              )}
            </div>
          )}
        </Section>
      </div>
    </div>
  );
}
