"use client";

import { ErrorBox, PageHeader, Section, Spinner, useApi } from "@/components/ui";

type Row = { id: number; ts: string; action: string; entity: string | null; message: string; before: Record<string, unknown> | null; after: Record<string, unknown> | null };

export default function Audit() {
  const a = useApi<Row[]>("/audit?limit=500");
  return (
    <div>
      <PageHeader title="🔐 Audit log" subtitle="Vsaka sprememba podatkov, pravil in vsak ponovni izračun — vedno veš, zakaj se je številka spremenila." />
      <ErrorBox error={a.error} />
      <Section>
        {!a.data ? <Spinner /> : (
          <ol className="space-y-0">
            {a.data.map((r) => (
              <li key={r.id} className="grid grid-cols-[110px_1fr] gap-3 border-b border-line py-2 text-sm last:border-0 sm:grid-cols-[150px_1fr]">
                <time className="num text-ink-3">{new Date(r.ts).toLocaleString("sl-SI", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}</time>
                <div>
                  <div>{r.message}</div>
                  {r.before && r.after && Object.keys(r.after).length > 0 && (
                    <div className="mt-0.5 font-mono text-xs text-ink-3">
                      {Object.keys(r.after).map((k) => <div key={k}>{k}: {String(r.before?.[k] ?? "—")} → {String(r.after?.[k] ?? "—")}</div>)}
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ol>
        )}
      </Section>
    </div>
  );
}
