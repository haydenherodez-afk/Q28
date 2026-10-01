"use client";

import { useEffect, useState } from "react";
import { useYear } from "@/components/AppShell";
import { Lines, StackedBars } from "@/components/charts";
import { ExplainView } from "@/components/Explain";
import { Alert, ErrorBox, Field, PageHeader, Section, Spinner, useApi } from "@/components/ui";
import { api } from "@/lib/api";
import { eur, toNum } from "@/lib/fmt";
import type { Explained, Profile } from "@/lib/types";

type Regime = { prispevki: string; dohodnina: string; davcna_osnova: string; drzavi_skupaj: string; neto: string; scheme: string };
type Row = { revenue: string; expenses: string; regimes: Record<"normiran" | "dejanski", Regime> };
type Calc = { items: Record<string, Explained>; warnings: string[]; next_year: Record<string, string> };

export default function WhatIf() {
  const { year } = useYear();
  const profile = useApi<Profile>("/profile");
  const [levels, setLevels] = useState("70000, 80000, 90000, 100000, 120000");
  const [ratio, setRatio] = useState("10");
  const [pending, setPending] = useState(false);
  const [rows, setRows] = useState<Row[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [one, setOne] = useState({ revenue: "70000", expenses: "7000" });
  const [calc, setCalc] = useState<Calc | null>(null);
  const [open, setOpen] = useState<string | null>("dohodnina");
  const regime = (profile.data?.regime ?? "normiran") as "normiran" | "dejanski";

  async function run() {
    setErr(null);
    try {
      const revenues = levels.split(/[,;\s]+/).map((s) => s.replace(/\./g, "").replace(",", ".")).filter(Boolean);
      const r = await api<{ rows: Row[] }>(`/tax/whatif?year=${year}`, { method: "POST", json: { revenues, expense_ratio: String(toNum(ratio) / 100), simulate_pending: pending } });
      setRows(r.rows);
    } catch (e) { setErr((e as Error).message); }
  }
  async function runOne() {
    setErr(null);
    try {
      setCalc(await api<Calc>(`/tax/calculate?year=${year}`, { method: "POST", json: { revenue: one.revenue, expenses: one.expenses, regime: "profile", simulate_pending: pending } }));
    } catch (e) { setErr((e as Error).message); }
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { run(); runOne(); }, [year, pending]);

  const stack = (rows ?? []).map((r) => {
    const g = r.regimes[regime];
    return { revenue: toNum(r.revenue), neto: toNum(g.neto), dohodnina: toNum(g.dohodnina), prispevki: toNum(g.prispevki), stroski: toNum(r.expenses) };
  });
  const lines = (rows ?? []).map((r) => ({ revenue: toNum(r.revenue), normiran: toNum(r.regimes.normiran.neto), dejanski: toNum(r.regimes.dejanski.neto) }));

  return (
    <div>
      <PageHeader title="What if? simulator" subtitle="Kaj mi ostane pri različnih prihodkih — vse izračuna davčni engine, za oba režima." />
      <ErrorBox error={err} />
      <Section className="mb-5">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-4">
          <div className="sm:col-span-2"><Field label="Letni prihodki (ločeno z vejico)"><input className="field num" value={levels} onChange={(e) => setLevels(e.target.value)} /></Field></div>
          <Field label="Dejanski stroški (% prihodkov)"><input className="field num" inputMode="decimal" value={ratio} onChange={(e) => setRatio(e.target.value)} /></Field>
          <div className="flex items-end"><button className="btn btn-primary w-full" onClick={run}>Izračunaj</button></div>
        </div>
        <label className="mt-3 flex items-start gap-2 text-sm">
          <input type="checkbox" className="mt-1" checked={pending} onChange={(e) => setPending(e.target.checked)} />
          <span>Simuliraj ZIURS (sprejet, a <b>še ne velja</b> — referendum): razvojna kapica 7.500 € na zavarovalno osnovo</span>
        </label>
        {pending && <div className="mt-2"><Alert kind="warning">Simulacija zakona, ki še ne velja. Ne uporabljaj za planiranje plačil.</Alert></div>}
      </Section>

      {!rows ? <Spinner /> : (
        <div className="grid gap-5 xl:grid-cols-2">
          <Section title={`Prihodek → obveznosti → neto (${regime === "normiran" ? "normiranec" : "dejanski stroški"})`}>
            <StackedBars x="revenue" data={stack} series={[
              { key: "neto", label: "Ostane tebi", color: "var(--series-1)" },
              { key: "dohodnina", label: "Dohodnina", color: "var(--series-2)" },
              { key: "prispevki", label: "Prispevki", color: "var(--series-3)" },
              { key: "stroski", label: "Stroški", color: "var(--series-4)" },
            ]} />
          </Section>
          <Section title="Neto ostanek: normiranec vs dejanski stroški">
            <Lines x="revenue" data={lines} series={[
              { key: "normiran", label: "Normiranec", color: "var(--series-1)" },
              { key: "dejanski", label: "Dejanski stroški", color: "var(--series-2)" },
            ]} />
          </Section>
          <Section title="Tabela" className="xl:col-span-2">
            <div className="-mx-2 overflow-x-auto">
              <table className="tbl">
                <thead>
                  <tr><th>Prihodki</th><th className="r">Stroški</th><th className="r">Prispevki</th><th className="r">Dohodnina (N)</th><th className="r">Ostane (N)</th><th className="r">Dohodnina (D)</th><th className="r">Ostane (D)</th><th>Bolje</th></tr>
                </thead>
                <tbody>
                  {rows.map((r) => {
                    const n = toNum(r.regimes.normiran.neto), d = toNum(r.regimes.dejanski.neto);
                    return (
                      <tr key={r.revenue}>
                        <td className="num font-semibold">{eur(r.revenue)}</td>
                        <td className="r">{eur(r.expenses)}</td>
                        <td className="r">{eur(r.regimes.normiran.prispevki)}</td>
                        <td className="r">{eur(r.regimes.normiran.dohodnina)}</td>
                        <td className="r font-semibold">{eur(r.regimes.normiran.neto)}</td>
                        <td className="r">{eur(r.regimes.dejanski.dohodnina)}</td>
                        <td className="r font-semibold">{eur(r.regimes.dejanski.neto)}</td>
                        <td className="whitespace-nowrap text-sm">{Math.abs(n - d) < 1 ? "enako" : n > d ? `normiranec +${eur(n - d)}` : `dejanski +${eur(d - n)}`}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="mt-2 text-xs text-ink-3">N = normiranec, D = dejanski stroški (dohodnina po lestvici, ob predpostavki, da je s.p. edini dohodek). Prispevki so enaki — odvisni so od zavarovalne osnove, ne od letošnjega prihodka.</p>
          </Section>
        </div>
      )}

      <Section title="🧮 Natančen izračun z razlago" className="mt-5">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Field label="Letni prihodki brez DDV"><input className="field num" value={one.revenue} onChange={(e) => setOne({ ...one, revenue: e.target.value })} /></Field>
          <Field label="Dejanski stroški brez DDV"><input className="field num" value={one.expenses} onChange={(e) => setOne({ ...one, expenses: e.target.value })} /></Field>
          <div className="flex items-end"><button className="btn btn-primary w-full" onClick={runOne}>Izračunaj</button></div>
        </div>
        {calc && (
          <div className="mt-4 grid gap-4 lg:grid-cols-3">
            <div className="space-y-1">
              {["prihodki", "normirani_odhodki", "odhodki", "davcna_osnova", "prispevki", "dohodnina", "drzavi_skupaj", "neto", "akontacija_naslednje_leto"]
                .filter((k) => calc.items[k]).map((k) => (
                  <button key={k} onClick={() => setOpen(k)} className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm ${open === k ? "bg-surface-2 font-semibold" : "hover:bg-surface-2"}`}>
                    <span>{calc.items[k].label}</span><span className="num">{eur(calc.items[k].value)}</span>
                  </button>
                ))}
            </div>
            <div className="lg:col-span-2">{open && calc.items[open] && <ExplainView e={calc.items[open]} />}</div>
          </div>
        )}
      </Section>
    </div>
  );
}
