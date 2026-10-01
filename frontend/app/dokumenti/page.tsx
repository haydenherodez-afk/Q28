"use client";

import { useRef, useState } from "react";
import { useYear } from "@/components/AppShell";
import { Alert, Badge, Empty, ErrorBox, PageHeader, Section, Spinner, useApi } from "@/components/ui";
import { api, openDocument } from "@/lib/api";
import { dateSl } from "@/lib/fmt";

type Doc = { id: number; filename: string; content_type: string; size: number; folder: string; year: number; uploaded_at: string };
type FursOut = { document: Record<string, unknown>; checks: { label: string; engine: string | null; furs: string | null; match: boolean }[]; all_match: boolean; profile_updates: Record<string, unknown>; note: string };

const FOLDERS: [string, string][] = [["racuni", "📄 računi"], ["stroski", "📄 stroški"], ["FURS", "📄 FURS"], ["OPSV", "📄 OPSV"], ["DDV", "📄 DDV"],
  ["pogodbe", "📄 pogodbe"], ["izpiski", "📄 bančni izpiski"], ["letni", "📄 letni obračuni"], ["drugo", "📄 drugo"]];
const LABELS: Record<string, string> = { regime: "Režim", activity_start: "Začetek dejavnosti", prev_year_turnover: "Prihodki preteklega leta",
  prev_year_insured_75: "Lani ≥ 75 % polno zavarovan", akontacija_annual: "Letna akontacija", business_name: "Naziv", tax_number: "Davčna številka" };

export default function Dokumenti() {
  const { year } = useYear();
  const [folder, setFolder] = useState("racuni");
  const docs = useApi<Doc[]>(`/documents?year=${year}`);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [furs, setFurs] = useState<FursOut | null>(null);
  const [applied, setApplied] = useState(false);
  const up = useRef<HTMLInputElement>(null);
  const fursRef = useRef<HTMLInputElement>(null);
  const list = (docs.data ?? []).filter((d) => d.folder === folder);

  async function upload(f: File) {
    setBusy(true); setErr(null);
    try {
      const fd = new FormData(); fd.append("file", f); fd.append("folder", folder); fd.append("year", String(year));
      await api("/documents", { method: "POST", body: fd }); docs.reload();
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  }
  async function importFurs(f: File) {
    setBusy(true); setErr(null); setFurs(null); setApplied(false);
    try {
      const fd = new FormData(); fd.append("file", f);
      setFurs(await api<FursOut>("/furs/import", { method: "POST", body: fd })); docs.reload();
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  }
  async function apply() {
    if (!furs) return;
    await api("/profile/apply", { method: "POST", json: furs.profile_updates });
    setApplied(true);
  }
  async function del(d: Doc) {
    if (!confirm(`Izbrišem ${d.filename}?`)) return;
    await api(`/documents/${d.id}`, { method: "DELETE" }); docs.reload();
  }

  return (
    <div>
      <PageHeader title={`🗂️ Document Vault ${year}`} subtitle="Vsi dokumenti na enem mestu. Uvozi obračun ali vlogo iz eDavkov — HericR nastavi profil in preveri, da se izračun ujema s FURS."
        actions={<>
          <input ref={fursRef} type="file" accept="application/pdf" className="hidden" onChange={(e) => e.target.files?.[0] && importFurs(e.target.files[0])} />
          <button className="btn" disabled={busy} onClick={() => fursRef.current?.click()}>⚖️ Uvozi FURS dokument</button>
          <input ref={up} type="file" className="hidden" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
          <button className="btn btn-primary" disabled={busy} onClick={() => up.current?.click()}>{busy ? "…" : "⬆️ Naloži"}</button>
        </>} />
      {err && <div className="mb-3"><Alert kind="error">{err}</Alert></div>}
      {furs && (
        <Section className="mb-5" title={<>Uvoz: {String(furs.document.title)} {furs.all_match ? <Badge kind="good">engine = FURS</Badge> : <Badge kind="error">razhajanje</Badge>}</>}>
          <div className="grid gap-4 lg:grid-cols-2">
            <table className="tbl">
              <thead><tr><th>Preverba</th><th className="r">HericR</th><th className="r">FURS</th><th /></tr></thead>
              <tbody>{furs.checks.map((c) => (
                <tr key={c.label}><td>{c.label}</td><td className="r">{c.engine ?? "—"}</td><td className="r">{c.furs ?? "—"}</td><td>{c.match ? "✅" : "❌"}</td></tr>
              ))}</tbody>
            </table>
            <div className="space-y-2 text-sm">
              <div className="font-semibold">Predlagane nastavitve</div>
              <ul className="space-y-1">{Object.entries(furs.profile_updates).map(([k, v]) => (
                <li key={k} className="flex justify-between gap-3"><span className="text-ink-2">{LABELS[k] ?? k}</span><span className="num font-medium">{String(v)}</span></li>
              ))}</ul>
              {furs.note && <Alert kind="info">{furs.note}</Alert>}
              {applied ? <Alert kind="good">Nastavitve so posodobljene.</Alert> : <button className="btn btn-primary" onClick={apply}>Uporabi nastavitve</button>}
            </div>
          </div>
        </Section>
      )}
      <div className="grid gap-5 md:grid-cols-4">
        <Section className="md:col-span-1">
          <div className="mb-2 font-semibold">📁 {year}</div>
          <ul className="space-y-0.5 text-sm">
            {FOLDERS.map(([k, l]) => {
              const n = (docs.data ?? []).filter((d) => d.folder === k).length;
              return (
                <li key={k}><button onClick={() => setFolder(k)} className={`flex w-full justify-between rounded-lg px-2 py-1.5 ${folder === k ? "bg-surface-2 font-semibold" : "hover:bg-surface-2"}`}>
                  <span>├── {l}</span><span className="text-ink-3">{n || ""}</span></button></li>
              );
            })}
          </ul>
        </Section>
        <Section className="md:col-span-3" title={FOLDERS.find(([k]) => k === folder)?.[1]}>
          <ErrorBox error={docs.error} />
          {!docs.data ? <Spinner /> : list.length === 0 ? <Empty>Mapa je prazna.</Empty> : (
            <table className="tbl">
              <thead><tr><th>Datoteka</th><th>Naloženo</th><th className="r">Velikost</th><th /></tr></thead>
              <tbody>{list.map((d) => (
                <tr key={d.id}>
                  <td className="font-medium">{d.filename}</td>
                  <td>{dateSl(d.uploaded_at)}</td>
                  <td className="r">{(d.size / 1024).toFixed(0)} kB</td>
                  <td className="whitespace-nowrap text-right">
                    <button className="btn px-2 py-1 text-xs" onClick={() => openDocument(d.id)}>Odpri</button>{" "}
                    <button className="btn btn-danger px-2 py-1 text-xs" onClick={() => del(d)} aria-label="Izbriši">✕</button>
                  </td>
                </tr>
              ))}</tbody>
            </table>
          )}
        </Section>
      </div>
    </div>
  );
}
