"use client";

import { useState } from "react";
import { useYear } from "@/components/AppShell";
import { Alert, Badge, ErrorBox, PageHeader, Section, Spinner, useApi } from "@/components/ui";
import { dateSl } from "@/lib/fmt";

type Rule = { id: string; title: string; formula: string; params: unknown; source: string; source_url: string | null; effective_from: string | null; effective_to: string | null; verified: boolean; verified_by: string[]; note: string; status: string };
type Selftest = { total: number; passed: number; failed: number; results: { id: string; label: string; expected: string; got: string | null; passed: boolean; error?: string }[] };

export default function Pravila() {
  const { year } = useYear();
  const rules = useApi<{ year: number; checked_on: string | null; rules: Rule[]; pending: Rule[] }>(`/rules?year=${year}`);
  const test = useApi<Selftest>("/rules/selftest");
  const [openId, setOpenId] = useState<string | null>(null);

  const RuleRow = ({ r }: { r: Rule }) => (
    <li className="py-3">
      <button className="flex w-full items-start justify-between gap-3 text-left" onClick={() => setOpenId(openId === r.id ? null : r.id)}>
        <div>
          <div className="font-medium">{r.title}</div>
          <div className="text-sm text-ink-2">{r.formula}</div>
        </div>
        <div className="shrink-0">{r.status !== "in_force" ? <Badge kind="warning">še ne velja</Badge> : r.verified ? <Badge kind="good">preverjeno</Badge> : <Badge kind="warning">preveri</Badge>}</div>
      </button>
      {openId === r.id && (
        <div className="mt-2 space-y-1 rounded-xl bg-surface-2 p-3 text-sm">
          <div><b>Vir:</b> {r.source} {r.source_url && <a className="text-accent underline" href={r.source_url} target="_blank" rel="noreferrer">↗</a>}</div>
          <div><b>Velja:</b> {dateSl(r.effective_from)} – {r.effective_to ? dateSl(r.effective_to) : "do preklica"}</div>
          {r.verified_by?.length > 0 && <div><b>Preverjeno v:</b> {r.verified_by.join(", ")}</div>}
          {r.note && <Alert kind="info">{r.note}</Alert>}
          <pre className="overflow-x-auto rounded-lg bg-surface p-2 text-xs">{JSON.stringify(r.params, null, 2)}</pre>
          <div className="font-mono text-xs text-ink-3">{r.id}</div>
        </div>
      )}
    </li>
  );

  return (
    <div>
      <PageHeader title="⚖️ Pravila & Testni način" subtitle={rules.data && <>Davčna pravila {year}, preverjena {dateSl(rules.data.checked_on)}. AI jih ne spreminja — samo bere.</>}
        actions={<button className="btn" onClick={test.reload}>🧪 Poženi teste</button>} />
      <ErrorBox error={rules.error} />
      <div className="grid gap-5 lg:grid-cols-5">
        <Section title="Pravila" className="lg:col-span-3">
          {!rules.data ? <Spinner /> : (
            <>
              <ul className="divide-y divide-line">{rules.data.rules.map((r) => <RuleRow key={r.id} r={r} />)}</ul>
              {rules.data.pending.length > 0 && (
                <>
                  <h3 className="mt-5 font-semibold">Sprejeto, a še ne velja</h3>
                  <ul className="divide-y divide-line">{rules.data.pending.map((r) => <RuleRow key={r.id} r={r} />)}</ul>
                </>
              )}
            </>
          )}
        </Section>
        <Section title="🧪 Zlati testi" className="lg:col-span-2">
          {!test.data ? <Spinner /> : (
            <div className="space-y-3">
              {test.data.failed === 0
                ? <Alert kind="good">{test.data.passed}/{test.data.total} testov uspešnih — kalkulator deluje pravilno.</Alert>
                : <Alert kind="error">❌ {test.data.failed} TESTI FAILED — davčni izračuni so morda napačni! Preveri spremembo pravil.</Alert>}
              <ul className="space-y-1 text-sm">
                {test.data.results.map((r) => (
                  <li key={r.id} className="flex items-start gap-2">
                    <span aria-hidden>{r.passed ? "✅" : "❌"}</span>
                    <span>{r.label}{!r.passed && <span className="block text-xs text-bad">pričakovano {r.expected}, dobljeno {r.got ?? r.error}</span>}</span>
                  </li>
                ))}
              </ul>
              <p className="text-xs text-ink-3">Pričakovane vrednosti so izračunane ročno iz zakona in uradnih zneskov. Ob vsaki spremembi pravil se testi poženejo samodejno in rezultat se zapiše v audit log.</p>
            </div>
          )}
        </Section>
      </div>
    </div>
  );
}
