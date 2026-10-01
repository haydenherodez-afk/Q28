"use client";

import { FormEvent, useState } from "react";
import { useYear } from "@/components/AppShell";
import { Alert, Badge, Empty, ErrorBox, Field, Modal, PageHeader, Section, Spinner, useApi } from "@/components/ui";
import { api } from "@/lib/api";
import { dateSl, eur, toNum } from "@/lib/fmt";
import type { Invoice } from "@/lib/types";
import ImportInvoices from "@/components/ImportInvoices";

const today = () => new Date().toISOString().slice(0, 10);
const plus = (iso: string, days: number) => { const d = new Date(iso); d.setDate(d.getDate() + days); return d.toISOString().slice(0, 10); };

function nextNumber(list: Invoice[], year: number) {
  const nums = list.map((i) => i.number.match(/^(.*?)(\d+)$/)).filter(Boolean) as RegExpMatchArray[];
  if (!nums.length) return `${year}-1`;
  const last = nums.sort((a, b) => Number(b[2]) - Number(a[2]))[0];
  return `${last[1]}${Number(last[2]) + 1}`;
}

const empty = (n: string) => ({
  number: n, customer: "", customer_tax_number: "", issue_date: today(), due_date: plus(today(), 15),
  net: "", vat_rate: "0.22", vat_note: "", notes: "",
});

export default function Prihodki() {
  const { year } = useYear();
  const list = useApi<Invoice[]>(`/invoices?year=${year}`);
  const [form, setForm] = useState<ReturnType<typeof empty> | null>(null);
  const [editId, setEditId] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const items = list.data ?? [];
  const total = items.reduce((s, i) => s + toNum(i.net), 0);
  const open = items.reduce((s, i) => s + Math.max(0, toNum(i.gross) - toNum(i.paid_amount)), 0);

  const vat = form ? Math.round(toNum(form.net) * toNum(form.vat_rate) * 100) / 100 : 0;

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!form) return;
    setErr(null);
    try {
      const body = { ...form, net: form.net, customer_tax_number: form.customer_tax_number || null, vat_note: form.vat_note || null, notes: form.notes || null, due_date: form.due_date || null };
      if (editId) await api(`/invoices/${editId}`, { method: "PUT", json: body });
      else await api("/invoices", { method: "POST", json: body });
      setForm(null); setEditId(null); list.reload();
    } catch (e) { setErr((e as Error).message); }
  }

  async function pay(i: Invoice) {
    const d = prompt("Datum plačila (YYYY-MM-DD)", today());
    if (!d) return;
    await api(`/invoices/${i.id}/pay?paid_date=${d}`, { method: "POST" });
    list.reload();
  }

  async function del(i: Invoice) {
    if (!confirm(`Izbrišem račun ${i.number}?`)) return;
    await api(`/invoices/${i.id}`, { method: "DELETE" });
    list.reload();
  }

  return (
    <div>
      <PageHeader title="Prihodki — izdani računi" subtitle={<>Letos brez DDV: <b className="num">{eur(total)}</b> · neplačano: <b className="num">{eur(open)}</b></>}
        actions={<>
          <ImportInvoices onDone={list.reload} />
          <button className="btn btn-primary" onClick={() => { setEditId(null); setForm(empty(nextNumber(items, year))); }}>+ Nov račun</button>
        </>} />
      <ErrorBox error={list.error} />
      <Section>
        {list.loading && !list.data ? <Spinner /> : items.length === 0 ? <Empty>Še ni izdanih računov za {year}.</Empty> : (
          <div className="-mx-2 overflow-x-auto">
            <table className="tbl">
              <thead><tr><th>Št.</th><th>Datum</th><th>Kupec</th><th className="r">Brez DDV</th><th className="r">DDV</th><th className="r">Z DDV</th><th>Status</th><th /></tr></thead>
              <tbody>
                {items.map((i) => {
                  const due = toNum(i.gross) - toNum(i.paid_amount);
                  const overdue = due > 0.01 && i.due_date && i.due_date < today();
                  return (
                    <tr key={i.id}>
                      <td className="font-medium">{i.number}</td>
                      <td className="whitespace-nowrap">{dateSl(i.issue_date)}</td>
                      <td>{i.customer || <span className="text-ink-3">—</span>}</td>
                      <td className="r">{eur(i.net)}</td>
                      <td className="r">{eur(i.vat)}</td>
                      <td className="r font-semibold">{eur(i.gross)}</td>
                      <td>{due <= 0.01 ? <Badge kind="good">plačano</Badge> : overdue ? <Badge kind="error">zapadlo</Badge> : <Badge kind="info">odprto</Badge>}</td>
                      <td className="whitespace-nowrap text-right">
                        {due > 0.01 && <button className="btn px-2 py-1 text-xs" onClick={() => pay(i)}>Plačano</button>}{" "}
                        <button className="btn px-2 py-1 text-xs" onClick={() => { setEditId(i.id); setForm({ number: i.number, customer: i.customer, customer_tax_number: i.customer_tax_number ?? "", issue_date: i.issue_date, due_date: i.due_date ?? "", net: i.net, vat_rate: i.vat_rate, vat_note: i.vat_note ?? "", notes: i.notes ?? "" }); }}>Uredi</button>{" "}
                        <button className="btn btn-danger px-2 py-1 text-xs" onClick={() => del(i)} aria-label="Izbriši">✕</button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Modal open={!!form} onClose={() => setForm(null)} title={editId ? "Uredi račun" : "Nov izdan račun"}>
        {form && (
          <form onSubmit={save} className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Številka računa"><input className="field" required value={form.number} onChange={(e) => setForm({ ...form, number: e.target.value })} /></Field>
            <Field label="Kupec"><input className="field" value={form.customer} onChange={(e) => setForm({ ...form, customer: e.target.value })} /></Field>
            <Field label="ID za DDV kupca"><input className="field" value={form.customer_tax_number} onChange={(e) => setForm({ ...form, customer_tax_number: e.target.value })} placeholder="SI12345678" /></Field>
            <Field label="Datum izdaje"><input className="field" type="date" required value={form.issue_date} onChange={(e) => setForm({ ...form, issue_date: e.target.value })} /></Field>
            <Field label="Rok plačila"><input className="field" type="date" value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} /></Field>
            <Field label="Znesek brez DDV (€)" hint="Za dobropis vpiši negativen znesek."><input className="field num" inputMode="decimal" required value={form.net} onChange={(e) => setForm({ ...form, net: e.target.value.replace(",", ".") })} /></Field>
            <Field label="Stopnja DDV">
              <select className="field" value={form.vat_rate} onChange={(e) => setForm({ ...form, vat_rate: e.target.value })}>
                <option value="0.22">22 %</option><option value="0.095">9,5 %</option><option value="0.05">5 %</option><option value="0">0 % (oproščeno / obrnjena obveznost)</option>
              </select>
            </Field>
            <Field label="DDV / skupaj"><div className="field num bg-surface-2">{eur(vat)} · {eur(toNum(form.net) + vat)}</div></Field>
            {form.vat_rate === "0" && (
              <div className="sm:col-span-2">
                <Field label="Razlog za 0 % DDV (obvezno na računu)" hint="npr. 'DDV ni obračunan v skladu s 76.a členom ZDDV-1' (gradbene storitve med zavezanci)">
                  <input className="field" value={form.vat_note} onChange={(e) => setForm({ ...form, vat_note: e.target.value })} />
                </Field>
              </div>
            )}
            <div className="sm:col-span-2"><Field label="Opombe"><input className="field" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></Field></div>
            {err && <div className="sm:col-span-2"><Alert kind="error">{err}</Alert></div>}
            <div className="flex justify-end gap-2 sm:col-span-2">
              <button type="button" className="btn" onClick={() => setForm(null)}>Prekliči</button>
              <button className="btn btn-primary">Shrani</button>
            </div>
          </form>
        )}
      </Modal>
    </div>
  );
}
