"use client";

import { useRef, useState } from "react";
import { api } from "@/lib/api";
import { dateSl, eur } from "@/lib/fmt";
import { Alert, Badge, Field, Modal } from "./ui";

type Row = { number: string; issue_date: string; due_date: string | null; buyer_name: string; seller_name: string; net: string; vat: string; gross: string; direction: string; duplicate: boolean; paid_date: string | null; pdf_name: string | null; warnings: string[] };
type Out = { dry_run: boolean; formats: string[]; found: number; created_invoices: number; created_expenses: number; skipped_duplicates: number; pdfs: number; by_year: Record<string, { issued_net: string; received_net: string; count: number }>; checks: { label: string; import: string; profile: string; match: boolean; difference: string }[]; warnings: string[]; rows: Row[] };

/** Uvoz računov za nazaj iz Evelope (eSLOG XML / ZIP ovojnica / Excel) ali drugega programa. */
export default function ImportInvoices({ onDone }: { onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [kind, setKind] = useState("auto");
  const [paidUntil, setPaidUntil] = useState("");
  const [res, setRes] = useState<Out | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const ref = useRef<HTMLInputElement>(null);

  async function run(dry: boolean, f = file) {
    if (!f) return;
    setBusy(true); setErr(null);
    try {
      const fd = new FormData();
      fd.append("file", f); fd.append("kind", kind); fd.append("dry_run", String(dry));
      if (paidUntil) fd.append("assume_paid_until", paidUntil);
      const r = await api<Out>("/import/invoices", { method: "POST", body: fd });
      setRes(r);
      if (!dry) onDone();
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  }

  return (
    <>
      <button className="btn" onClick={() => { setOpen(true); setRes(null); setFile(null); }}>⬇️ Uvozi iz Evelope</button>
      <Modal open={open} onClose={() => setOpen(false)} title="Uvoz računov za nazaj" wide>
        <div className="space-y-4 text-sm">
          <Alert kind="info">
            V Evelope izvozi račune kot <b>e-račun XML (eSLOG 2.0)</b> ali <b>ZIP ovojnico</b> (najboljše: priložijo se tudi PDF-ji) ali kot <b>Excel</b>.
            Podprti so tudi UBL/Peppol XML in CSV iz drugih programov. Podvojeni računi se preskočijo, zato lahko uvoz ponoviš kadarkoli.
          </Alert>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <Field label="Datoteka">
              <input ref={ref} type="file" accept=".xml,.zip,.xlsx,.csv" className="hidden" onChange={(e) => { const f = e.target.files?.[0] ?? null; setFile(f); setRes(null); if (f) run(true, f); }} />
              <button className="btn w-full" onClick={() => ref.current?.click()}>{file ? file.name : "Izberi datoteko…"}</button>
            </Field>
            <Field label="Vrsta računov">
              <select className="field" value={kind} onChange={(e) => setKind(e.target.value)}>
                <option value="auto">Samodejno (po davčni številki)</option><option value="issued">Izdani (prihodki)</option><option value="received">Prejeti (stroški)</option>
              </select>
            </Field>
            <Field label="Plačani so vsi z rokom do" hint="Izvoz XML ne vsebuje plačil. Ostale poveži z bančnim izpiskom.">
              <input className="field" type="date" value={paidUntil} onChange={(e) => setPaidUntil(e.target.value)} />
            </Field>
          </div>
          {file && <button className="btn" onClick={() => run(true)} disabled={busy}>{busy ? "Berem…" : "Osveži predogled"}</button>}
          {err && <Alert kind="error">{err}</Alert>}
          {res && (
            <div className="space-y-3">
              {res.dry_run ? (
                <Alert kind="info">Predogled ({res.formats.join(", ")}): najdenih {res.found} računov, {res.skipped_duplicates} že obstaja, {res.pdfs} PDF prilog. Nič še ni shranjeno.</Alert>
              ) : (
                <Alert kind="good">Uvoženo: {res.created_invoices} izdanih in {res.created_expenses} prejetih računov ({res.skipped_duplicates} podvojenih preskočenih).</Alert>
              )}
              <div className="flex flex-wrap gap-2">
                {Object.entries(res.by_year).map(([y, v]) => (
                  <div key={y} className="rounded-xl bg-surface-2 px-3 py-2">
                    <div className="text-xs text-ink-2">{y} · {v.count} računov</div>
                    <div className="num font-semibold">prihodki {eur(v.issued_net)}{Number(v.received_net) ? <> · stroški {eur(v.received_net)}</> : null}</div>
                  </div>
                ))}
              </div>
              {res.checks.map((c) => (
                <Alert key={c.label} kind={c.match ? "good" : "warning"}>
                  {c.label}: uvoz {eur(c.import)} vs nastavitve {eur(c.profile)} {c.match ? "— ujema se ✅" : `— razlika ${eur(c.difference)} (manjkajoči ali odvečni računi?)`}
                </Alert>
              ))}
              {res.warnings.length > 0 && <Alert kind="warning">{res.warnings.slice(0, 5).join(" · ")}{res.warnings.length > 5 && ` … (+${res.warnings.length - 5})`}</Alert>}
              <div className="max-h-72 overflow-auto rounded-xl border border-line">
                <table className="tbl">
                  <thead><tr><th>Št.</th><th>Datum</th><th>Partner</th><th className="r">Brez DDV</th><th className="r">Z DDV</th><th /></tr></thead>
                  <tbody>{res.rows.map((r, i) => (
                    <tr key={i} className={r.duplicate ? "opacity-50" : ""}>
                      <td className="font-medium">{r.number}</td>
                      <td>{dateSl(r.issue_date)}</td>
                      <td>{r.direction === "issued" ? r.buyer_name : r.seller_name}</td>
                      <td className="r">{eur(r.net)}</td>
                      <td className="r">{eur(r.gross)}</td>
                      <td className="whitespace-nowrap">
                        {r.duplicate ? <Badge kind="info">že obstaja</Badge> : r.direction === "issued" ? <Badge kind="good">prihodek</Badge> : <Badge kind="warning">strošek</Badge>}
                        {r.paid_date && <> <Badge kind="good">plačano</Badge></>} {r.pdf_name && "📄"} {r.warnings.length > 0 && <span title={r.warnings.join("; ")}>⚠️</span>}
                      </td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
              {res.dry_run && res.found - res.skipped_duplicates > 0 && (
                <div className="flex justify-end"><button className="btn btn-primary" onClick={() => run(false)} disabled={busy}>{busy ? "Uvažam…" : `✅ Uvozi ${res.found - res.skipped_duplicates} računov`}</button></div>
              )}
            </div>
          )}
        </div>
      </Modal>
    </>
  );
}
