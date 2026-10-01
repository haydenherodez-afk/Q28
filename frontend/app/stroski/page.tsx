"use client";

import { FormEvent, useRef, useState } from "react";
import { useYear } from "@/components/AppShell";
import { Alert, Badge, Empty, ErrorBox, Field, Modal, PageHeader, Section, Spinner, useApi } from "@/components/ui";
import { api, openDocument } from "@/lib/api";
import { dateSl, eur, toNum } from "@/lib/fmt";
import type { Expense } from "@/lib/types";

const CATS = ["material", "orodje in material", "gorivo", "programska oprema", "telekomunikacije", "storitve", "najemnina",
  "zavarovanje", "potni stroški", "izobraževanje", "oprema", "pisarna", "reprezentanca", "bančni stroški", "drugo"];
const today = () => new Date().toISOString().slice(0, 10);

type Form = {
  supplier: string; supplier_tax_number: string; invoice_number: string; date: string; net: string; vat: string; gross: string;
  category: string; vat_deductible: boolean; private_flag: boolean; notes: string; document_id: number | null; source: string;
};
const empty = (): Form => ({ supplier: "", supplier_tax_number: "", invoice_number: "", date: today(), net: "", vat: "", gross: "",
  category: "", vat_deductible: true, private_flag: false, notes: "", document_id: null, source: "manual" });

type ScanOut = { proposal: Record<string, string | number | boolean | null>; checks: { label: string; ok: boolean }[]; needs_review: boolean; document_id: number };

export default function Stroski() {
  const { year } = useYear();
  const list = useApi<Expense[]>(`/expenses?year=${year}`);
  const [form, setForm] = useState<Form | null>(null);
  const [editId, setEditId] = useState<number | null>(null);
  const [checks, setChecks] = useState<ScanOut["checks"] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [scanning, setScanning] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const items = list.data ?? [];
  const biz = items.filter((e) => !e.private_flag);
  const total = biz.reduce((s, e) => s + toNum(e.net), 0);
  const vatIn = biz.filter((e) => e.vat_deductible).reduce((s, e) => s + toNum(e.vat), 0);

  async function scan(file: File) {
    setScanning(true); setErr(null);
    try {
      const fd = new FormData();
      fd.append("file", file); fd.append("folder", "stroski"); fd.append("year", String(year));
      const doc = await api<{ id: number }>("/documents", { method: "POST", body: fd });
      try {
        const r = await api<ScanOut>(`/scan/${doc.id}`, { method: "POST" });
        const p = r.proposal;
        setChecks(r.checks);
        setEditId(null);
        setForm({
          supplier: String(p.supplier ?? ""), supplier_tax_number: String(p.supplier_tax_number ?? ""), invoice_number: String(p.invoice_number ?? ""),
          date: String(p.date ?? today()), net: String(p.net ?? ""), vat: String(p.vat ?? ""), gross: String(p.gross ?? ""),
          category: String(p.category ?? ""), vat_deductible: !p.possibly_private, private_flag: Boolean(p.possibly_private),
          notes: String(p.notes ?? ""), document_id: doc.id, source: "scan",
        });
      } catch (e) {
        // AI ni na voljo: dokument je shranjen, podatke vnesi ročno
        setErr(`${(e as Error).message} — dokument je shranjen, vnesi podatke ročno.`);
        setChecks(null);
        setForm({ ...empty(), document_id: doc.id });
      }
    } catch (e) { setErr((e as Error).message); } finally { setScanning(false); }
  }

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!form) return;
    setErr(null);
    const body = {
      ...form, net: form.net || null, vat: form.vat || null, gross: form.gross || null,
      supplier_tax_number: form.supplier_tax_number || null, invoice_number: form.invoice_number || null,
      category: form.category || null, notes: form.notes || null,
    };
    try {
      if (editId) await api(`/expenses/${editId}`, { method: "PUT", json: body });
      else if (form.source === "scan") await api("/scan/confirm", { method: "POST", json: body });
      else await api("/expenses", { method: "POST", json: body });
      setForm(null); setEditId(null); setChecks(null); list.reload();
    } catch (e) { setErr((e as Error).message); }
  }

  async function del(x: Expense) {
    if (!confirm(`Izbrišem strošek ${x.supplier}?`)) return;
    await api(`/expenses/${x.id}`, { method: "DELETE" });
    list.reload();
  }

  return (
    <div>
      <PageHeader title="Stroški — prejeti računi"
        subtitle={<>Poslovni stroški brez DDV: <b className="num">{eur(total)}</b> · vstopni DDV za odbitek: <b className="num">{eur(vatIn)}</b></>}
        actions={<>
          <input ref={fileRef} type="file" accept="application/pdf,image/*" capture="environment" className="hidden" onChange={(e) => e.target.files?.[0] && scan(e.target.files[0])} />
          <button className="btn" onClick={() => fileRef.current?.click()} disabled={scanning}>{scanning ? "Berem račun…" : "📷 Skeniraj račun"}</button>
          <button className="btn btn-primary" onClick={() => { setEditId(null); setChecks(null); setForm(empty()); }}>+ Ročni vnos</button>
        </>} />
      <ErrorBox error={list.error} />
      {err && !form && <div className="mb-3"><Alert kind="error">{err}</Alert></div>}
      <Section>
        {list.loading && !list.data ? <Spinner /> : items.length === 0 ? <Empty>Ni stroškov za {year}. Skeniraj račun ali ga vnesi ročno.</Empty> : (
          <div className="-mx-2 overflow-x-auto">
            <table className="tbl">
              <thead><tr><th>Datum</th><th>Dobavitelj</th><th>Kategorija</th><th className="r">Brez DDV</th><th className="r">DDV</th><th className="r">Skupaj</th><th /><th /></tr></thead>
              <tbody>
                {items.map((x) => (
                  <tr key={x.id} className={x.private_flag ? "opacity-60" : ""}>
                    <td className="whitespace-nowrap">{dateSl(x.date)}</td>
                    <td><span className="font-medium">{x.supplier || "—"}</span>{x.invoice_number && <span className="block text-xs text-ink-3">{x.invoice_number}</span>}</td>
                    <td className="text-ink-2">{x.category ?? "—"}</td>
                    <td className="r">{eur(x.net)}</td>
                    <td className="r">{eur(x.vat)}</td>
                    <td className="r font-semibold">{eur(x.gross)}</td>
                    <td className="whitespace-nowrap">
                      {x.private_flag && <Badge kind="warning">zasebno</Badge>} {x.source === "scan" && <Badge kind="info">sken</Badge>} {!x.document_id && <Badge kind="warning">brez dokumenta</Badge>}
                    </td>
                    <td className="whitespace-nowrap text-right">
                      {x.document_id && <button className="btn px-2 py-1 text-xs" onClick={() => openDocument(x.document_id!)} aria-label="Odpri račun">📄</button>}{" "}
                      <button className="btn px-2 py-1 text-xs" onClick={() => { setChecks(null); setEditId(x.id); setForm({ supplier: x.supplier, supplier_tax_number: x.supplier_tax_number ?? "", invoice_number: x.invoice_number ?? "", date: x.date, net: x.net, vat: x.vat, gross: x.gross, category: x.category ?? "", vat_deductible: x.vat_deductible, private_flag: x.private_flag, notes: x.notes ?? "", document_id: x.document_id, source: x.source }); }}>Uredi</button>{" "}
                      <button className="btn btn-danger px-2 py-1 text-xs" onClick={() => del(x)} aria-label="Izbriši">✕</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Modal open={!!form} onClose={() => { setForm(null); setErr(null); }} title={form?.source === "scan" && !editId ? "Potrdi prebran račun" : editId ? "Uredi strošek" : "Nov strošek"}>
        {form && (
          <form onSubmit={save} className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {checks && (
              <div className="space-y-1 sm:col-span-2">
                {checks.map((c) => <Alert key={c.label} kind={c.ok ? "good" : "warning"}>{c.label}</Alert>)}
              </div>
            )}
            <Field label="Dobavitelj"><input className="field" required value={form.supplier} onChange={(e) => setForm({ ...form, supplier: e.target.value })} /></Field>
            <Field label="Št. računa"><input className="field" value={form.invoice_number} onChange={(e) => setForm({ ...form, invoice_number: e.target.value })} /></Field>
            <Field label="Datum"><input className="field" type="date" required value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} /></Field>
            <Field label="Kategorija">
              <select className="field" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
                <option value="">— izberi —</option>{CATS.map((c) => <option key={c}>{c}</option>)}
              </select>
            </Field>
            <Field label="Brez DDV (€)"><input className="field num" inputMode="decimal" value={form.net} onChange={(e) => setForm({ ...form, net: e.target.value.replace(",", ".") })} /></Field>
            <Field label="DDV (€)"><input className="field num" inputMode="decimal" value={form.vat} onChange={(e) => setForm({ ...form, vat: e.target.value.replace(",", ".") })} /></Field>
            <Field label="Skupaj z DDV (€)" hint="Vpiši vsaj dva od treh zneskov."><input className="field num" inputMode="decimal" value={form.gross} onChange={(e) => setForm({ ...form, gross: e.target.value.replace(",", ".") })} /></Field>
            <div className="space-y-2 pt-6 text-sm">
              <label className="flex items-center gap-2"><input type="checkbox" checked={form.vat_deductible} onChange={(e) => setForm({ ...form, vat_deductible: e.target.checked })} /> DDV lahko odbijem</label>
              <label className="flex items-center gap-2"><input type="checkbox" checked={form.private_flag} onChange={(e) => setForm({ ...form, private_flag: e.target.checked })} /> Zasebno (ni poslovni strošek)</label>
            </div>
            <div className="sm:col-span-2"><Field label="Opombe"><input className="field" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></Field></div>
            {err && <div className="sm:col-span-2"><Alert kind="warning">{err}</Alert></div>}
            <div className="flex justify-end gap-2 sm:col-span-2">
              <button type="button" className="btn" onClick={() => setForm(null)}>Prekliči</button>
              <button className="btn btn-primary">{form.source === "scan" && !editId ? `✅ Dodaj strošek ${form.gross ? eur(form.gross) : ""}` : "Shrani"}</button>
            </div>
          </form>
        )}
      </Modal>
    </div>
  );
}
