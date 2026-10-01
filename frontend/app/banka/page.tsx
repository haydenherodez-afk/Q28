"use client";

import { FormEvent, useRef, useState } from "react";
import { useYear } from "@/components/AppShell";
import { Alert, Badge, Empty, ErrorBox, Field, PageHeader, Section, Spinner, useApi } from "@/components/ui";
import { api } from "@/lib/api";
import { dateSl, eur, toNum } from "@/lib/fmt";
import type { Invoice } from "@/lib/types";

type Tx = { id: number; date: string; amount: string; counterparty: string; description: string; reference: string | null; category: string | null; matched_invoice_id: number | null; matched_expense_id: number | null };
type ImportOut = { format: string; added: number; skipped_duplicates: number; matched_invoices: number; tax_payments: number; closing_balance: string | null; warnings: string[] };

const TAX = ["prispevki", "akontacija", "ddv", "dohodnina", "drugo"];
const CATS = ["prihodek", "gorivo", "programska oprema", "telekomunikacije", "orodje in material", "zavarovanje", "storitve", "bančni stroški", "zasebno", "dvig", ...TAX];

export default function Banka() {
  const { year } = useYear();
  const txs = useApi<Tx[]>(`/bank/transactions?year=${year}`);
  const invoices = useApi<Invoice[]>(`/invoices?year=${year}`);
  const [result, setResult] = useState<ImportOut | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [bal, setBal] = useState({ date: new Date().toISOString().slice(0, 10), balance: "" });
  const [filter, setFilter] = useState<"vse" | "nerazporejeno">("vse");
  const ref = useRef<HTMLInputElement>(null);

  async function upload(f: File) {
    setBusy(true); setErr(null); setResult(null);
    try {
      const fd = new FormData(); fd.append("file", f);
      setResult(await api<ImportOut>("/bank/import", { method: "POST", body: fd }));
      txs.reload(); invoices.reload();
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  }

  async function patch(t: Tx, body: Record<string, unknown>) {
    await api(`/bank/transactions/${t.id}`, { method: "PATCH", json: body });
    txs.reload(); invoices.reload();
  }

  async function saveBalance(e: FormEvent) {
    e.preventDefault();
    await api("/balances", { method: "POST", json: { date: bal.date, balance: bal.balance.replace(",", ".") } });
    setBal({ ...bal, balance: "" });
    alert("Stanje shranjeno.");
  }

  const openInv = (invoices.data ?? []).filter((i) => toNum(i.gross) - toNum(i.paid_amount) > 0.01);
  const rows = (txs.data ?? []).filter((t) => filter === "vse" || (!t.category || t.category === "zasebno?" || (toNum(t.amount) > 0 && !t.matched_invoice_id)));

  return (
    <div>
      <PageHeader title="Banka" subtitle="Uvozi izpisek (camt.053 XML ali CSV iz spletne banke). Prilivi se povežejo z računi, plačila FURS se evidentirajo samodejno."
        actions={<>
          <input ref={ref} type="file" accept=".xml,.csv,.txt,text/csv,application/xml" className="hidden" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
          <button className="btn btn-primary" disabled={busy} onClick={() => ref.current?.click()}>{busy ? "Uvažam…" : "⬆️ Uvozi izpisek"}</button>
        </>} />
      {err && <div className="mb-3"><Alert kind="error">{err}</Alert></div>}
      {result && (
        <div className="mb-4"><Alert kind="good">
          Uvoženo {result.added} transakcij ({result.format}); {result.skipped_duplicates} podvojenih preskočenih; povezanih {result.matched_invoices} računov; {result.tax_payments} plačil FURS.
          {result.closing_balance && <> Končno stanje: <b>{eur(result.closing_balance)}</b>.</>}
          {result.warnings.length > 0 && <div className="mt-1 text-xs">{result.warnings.length} vrstic ni bilo mogoče prebrati.</div>}
        </Alert></div>
      )}
      <div className="grid gap-5 lg:grid-cols-4">
        <Section title="Transakcije" className="lg:col-span-3"
          actions={<select className="field w-auto py-1 text-sm" value={filter} onChange={(e) => setFilter(e.target.value as typeof filter)}><option value="vse">Vse</option><option value="nerazporejeno">Za razporediti</option></select>}>
          <ErrorBox error={txs.error} />
          {txs.loading && !txs.data ? <Spinner /> : rows.length === 0 ? <Empty>Ni transakcij. Uvozi bančni izpisek.</Empty> : (
            <div className="-mx-2 overflow-x-auto">
              <table className="tbl">
                <thead><tr><th>Datum</th><th>Partner / namen</th><th className="r">Znesek</th><th>Kategorija</th><th>Povezava</th></tr></thead>
                <tbody>
                  {rows.map((t) => {
                    const amt = toNum(t.amount);
                    return (
                      <tr key={t.id}>
                        <td className="whitespace-nowrap">{dateSl(t.date)}</td>
                        <td><span className="font-medium">{t.counterparty || "—"}</span><span className="block max-w-xs truncate text-xs text-ink-3">{t.description}</span></td>
                        <td className={`r font-semibold ${amt > 0 ? "text-good" : ""}`}>{eur(t.amount)}</td>
                        <td>
                          <select className="field py-1 text-xs" value={t.category ?? ""} onChange={(e) => {
                            const v = e.target.value;
                            patch(t, TAX.includes(v) && amt < 0 ? { tax_kind: v } : { category: v });
                          }}>
                            <option value="">—</option>{t.category === "zasebno?" && <option value="zasebno?">zasebno?</option>}
                            {CATS.map((c) => <option key={c}>{c}</option>)}
                          </select>
                        </td>
                        <td className="text-xs">
                          {t.matched_invoice_id ? <Badge kind="good">račun #{t.matched_invoice_id}</Badge>
                            : amt > 0 ? (
                              <select className="field py-1 text-xs" value="" onChange={(e) => e.target.value && patch(t, { matched_invoice_id: Number(e.target.value) })}>
                                <option value="">poveži z računom…</option>
                                {openInv.map((i) => <option key={i.id} value={i.id}>{i.number} · {i.customer} · {eur(toNum(i.gross) - toNum(i.paid_amount))}</option>)}
                              </select>
                            ) : TAX.includes(t.category ?? "") ? <Badge kind="info">plačilo FURS</Badge> : null}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Section>
        <Section title="Stanje na TRR">
          <form onSubmit={saveBalance} className="space-y-3">
            <p className="text-sm text-ink-2">Če banka ne izvozi stanja, ga vnesi ročno — potrebno je za davčno rezervo in koledar.</p>
            <Field label="Datum"><input className="field" type="date" value={bal.date} onChange={(e) => setBal({ ...bal, date: e.target.value })} /></Field>
            <Field label="Stanje (€)"><input className="field num" inputMode="decimal" required value={bal.balance} onChange={(e) => setBal({ ...bal, balance: e.target.value })} /></Field>
            <button className="btn btn-primary w-full">Shrani stanje</button>
          </form>
        </Section>
      </div>
    </div>
  );
}
