"use client";

import Link from "next/link";
import { useYear } from "@/components/AppShell";
import { Alert, Badge, ErrorBox, PageHeader, Section, Spinner, useApi } from "@/components/ui";
import { api } from "@/lib/api";
import type { Finding } from "@/lib/types";

const LINK: Record<string, string> = { invoice: "/prihodki", expense: "/stroski", bank: "/banka", calendar: "/koledar" };

export default function Napake() {
  const { year } = useYear();
  const m = useApi<{ count: number; items: Finding[] }>(`/mistakes?year=${year}`);
  const groups = ["error", "warning", "info"] as const;
  return (
    <div>
      <PageHeader title="🕵️ Find mistakes" subtitle="Samodejne kontrole: neplačani računi, plačila brez računov, podvojeni stroški, napačen DDV, manjkajoči podatki, zasebni stroški, zamujeni roki, pragovi."
        actions={<button className="btn" onClick={m.reload}>Ponovno preveri</button>} />
      <ErrorBox error={m.error} />
      {!m.data ? <Spinner /> : m.data.count === 0 ? <Alert kind="good">Ni najdenih napak. Odlično!</Alert> : (
        <div className="space-y-5">
          {groups.map((g) => {
            const items = m.data!.items.filter((f) => f.severity === g);
            if (!items.length) return null;
            return (
              <Section key={g} title={<><Badge kind={g} /> <span className="ml-1">{items.length}</span></>}>
                <ul className="divide-y divide-line">
                  {items.map((f) => (
                    <li key={f.key} className="flex items-start justify-between gap-3 py-2.5">
                      <div className="min-w-0 text-sm">
                        <div className="font-medium">❌ {f.title}</div>
                        <div className="text-ink-2">{f.detail}</div>
                      </div>
                      <div className="flex shrink-0 gap-1">
                        {f.entity && LINK[f.entity] && <Link className="btn px-2 py-1 text-xs" href={LINK[f.entity]}>Odpri</Link>}
                        <button className="btn px-2 py-1 text-xs" title="Označi kot rešeno / ni napaka" onClick={async () => { await api(`/alerts/dismiss?key=${encodeURIComponent(f.key)}`, { method: "POST" }); m.reload(); }}>✓</button>
                      </div>
                    </li>
                  ))}
                </ul>
              </Section>
            );
          })}
        </div>
      )}
    </div>
  );
}
