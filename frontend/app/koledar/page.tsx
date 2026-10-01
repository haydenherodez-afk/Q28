"use client";

import { useState } from "react";
import { useYear } from "@/components/AppShell";
import { Alert, Badge, Empty, ErrorBox, Field, Modal, PageHeader, Section, Spinner, useApi } from "@/components/ui";
import { api } from "@/lib/api";
import { agoDays, dateSl, eur, inDays, lateDays, toNum } from "@/lib/fmt";
import type { CalItem } from "@/lib/types";

type Cal = { today: string; balance: string | null; safety_buffer: string; items: CalItem[]; next: CalItem[] };
const STATUS: Record<string, [string, string]> = {
  placano: ["good", "plačano"], zamujeno: ["error", "zamujeno"], odprto: ["info", "odprto"], ni_obveznosti: ["good", "ni obveznosti"],
};
const KIND_ICON: Record<string, string> = { prispevki: "🔴", akontacija: "🟠", ddv: "🔵", obracun: "📝", dohodnina: "🟣" };

export default function Koledar() {
  const { year } = useYear();
  const cal = useApi<Cal>(`/calendar?year=${year}`);
  const [show, setShow] = useState<"odprto" | "vse">("odprto");
  const [pay, setPay] = useState<CalItem | null>(null);
  const [payForm, setPayForm] = useState({ date: new Date().toISOString().slice(0, 10), amount: "" });
  const [err, setErr] = useState<string | null>(null);
  const items = (cal.data?.items ?? []).filter((i) => show === "vse" || i.status === "odprto" || i.status === "zamujeno");
  const next = cal.data?.next[0];

  async function savePayment() {
    if (!pay) return;
    setErr(null);
    try {
      await api("/payments", { method: "POST", json: { date: payForm.date, kind: pay.kind === "obracun" ? "dohodnina" : pay.kind, period: pay.period, amount: payForm.amount.replace(",", ".") } });
      setPay(null); cal.reload();
    } catch (e) { setErr((e as Error).message); }
  }

  return (
    <div>
      <PageHeader title="Smart Tax Calendar" subtitle={cal.data && <>Stanje na TRR: <b className="num">{eur(cal.data.balance)}</b> · varnostna rezerva {eur(cal.data.safety_buffer)}</>}
        actions={<select className="field w-auto" value={show} onChange={(e) => setShow(e.target.value as typeof show)}><option value="odprto">Odprte obveznosti</option><option value="vse">Vse (tudi plačane)</option></select>} />
      <ErrorBox error={cal.error} />
      {cal.loading && !cal.data && <Spinner />}
      {next && (
        <div className="card mb-5 p-5">
          <div className="text-sm font-semibold uppercase tracking-wide text-ink-2">
            {(next.days_until < 0 ? `zamujeno ${lateDays(-next.days_until)}` : next.days_until === 0 ? "danes" : inDays(next.days_until)).toUpperCase()}
          </div>
          <div className="mt-1 text-xl font-bold">{KIND_ICON[next.kind]} {next.title}</div>
          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div><div className="text-xs text-ink-2">Predviden znesek</div><div className="num text-2xl font-bold">{eur(next.amount)}</div></div>
            <div><div className="text-xs text-ink-2">Stanje na TRR</div><div className="num text-2xl font-bold">{eur(cal.data?.balance)}</div></div>
            <div><div className="text-xs text-ink-2">Po plačilu bo ostalo</div><div className="num text-2xl font-bold">{eur(next.balance_after)}</div></div>
          </div>
          {next.cash_warning && <div className="mt-3"><Alert kind="warning">{next.cash_warning}</Alert></div>}
          <div className="mt-2 text-xs text-ink-3">{next.explain}</div>
        </div>
      )}
      <Section>
        {items.length === 0 ? <Empty>Ni obveznosti v izbranem pogledu.</Empty> : (
          <div className="-mx-2 overflow-x-auto">
            <table className="tbl">
              <thead><tr><th>Rok</th><th>Obveznost</th><th className="r">Znesek</th><th className="r">Plačano</th><th>Status</th><th>Po plačilu na TRR</th><th /></tr></thead>
              <tbody>
                {items.map((i) => (
                  <tr key={i.kind + i.period}>
                    <td className="whitespace-nowrap">{dateSl(i.due_date)}<span className="block text-xs text-ink-3">{i.days_until === 0 ? "danes" : i.days_until > 0 ? inDays(i.days_until) : agoDays(-i.days_until)}</span></td>
                    <td><span className="font-medium">{KIND_ICON[i.kind]} {i.title}</span><span className="block text-xs text-ink-3">{i.explain}</span></td>
                    <td className="r font-semibold">{i.amount ? eur(i.amount) : "—"}{i.estimated && <span className="text-ink-3" title="ocena">*</span>}</td>
                    <td className="r">{toNum(i.paid) ? eur(i.paid) : "—"}</td>
                    <td><Badge kind={STATUS[i.status][0]}>{STATUS[i.status][1]}</Badge></td>
                    <td className="text-xs">{i.balance_after && <span className={`num ${i.cash_warning ? "font-semibold text-warn" : ""}`}>{eur(i.balance_after)}</span>}</td>
                    <td>{(i.status === "odprto" || i.status === "zamujeno") && i.kind !== "obracun" && (
                      <button className="btn whitespace-nowrap px-2 py-1 text-xs" onClick={() => { setPay(i); setPayForm({ date: new Date().toISOString().slice(0, 10), amount: String(Math.max(0, toNum(i.amount) - toNum(i.paid)).toFixed(2)) }); }}>Plačal sem</button>
                    )}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 px-2 text-xs text-ink-3">* ocena — dejanski znesek bo znan po koncu obdobja.</p>
          </div>
        )}
      </Section>
      <Modal open={!!pay} onClose={() => setPay(null)} title={`Evidentiraj plačilo: ${pay?.title ?? ""}`}>
        <div className="space-y-3">
          <Field label="Datum plačila"><input className="field" type="date" value={payForm.date} onChange={(e) => setPayForm({ ...payForm, date: e.target.value })} /></Field>
          <Field label="Znesek (€)"><input className="field num" value={payForm.amount} onChange={(e) => setPayForm({ ...payForm, amount: e.target.value })} /></Field>
          {err && <Alert kind="error">{err}</Alert>}
          <div className="flex justify-end gap-2"><button className="btn" onClick={() => setPay(null)}>Prekliči</button><button className="btn btn-primary" onClick={savePayment}>Shrani</button></div>
        </div>
      </Modal>
    </div>
  );
}
