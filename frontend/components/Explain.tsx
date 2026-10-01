"use client";

import { useState } from "react";
import { eur } from "@/lib/fmt";
import type { Explained } from "@/lib/types";
import { Alert, Badge, Modal } from "./ui";

/** "ⓘ Kako je izračunano?" — celotna pot do številke, s pravili in viri. */
export function ExplainView({ e }: { e: Explained }) {
  return (
    <div className="space-y-4 text-sm">
      <div className="rounded-xl bg-surface-2 p-4">
        <div className="text-ink-2">{e.label}</div>
        <div className="num text-3xl font-bold">{eur(e.value)}</div>
        {e.formula && <div className="mt-2 text-ink-2"><span className="font-medium text-ink">Formula:</span> {e.formula}</div>}
      </div>
      {e.steps.length > 0 && (
        <div>
          <div className="mb-1 font-semibold">Izračun</div>
          <table className="tbl">
            <tbody>
              {e.steps.map((s, i) => (
                <tr key={i}>
                  <td>
                    {s.label}
                    {s.note && <div className="text-xs text-ink-3">{s.note}</div>}
                  </td>
                  <td className="r font-medium">{s.value !== null ? eur(s.value) : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {e.warnings?.map((w, i) => <Alert key={i} kind="warning">{w}</Alert>)}
      {e.sources && e.sources.length > 0 && (
        <div>
          <div className="mb-1 font-semibold">Uporabljena pravila in viri</div>
          <ul className="space-y-2">
            {e.sources.map((s) => (
              <li key={s.rule_id} className="rounded-xl border border-line p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{s.title}</span>
                  {s.verified ? <Badge kind="good">preverjeno</Badge> : <Badge kind="warning">preveri pri FURS</Badge>}
                </div>
                <div className="mt-1 text-ink-2">{s.source}</div>
                {s.note && <div className="mt-1 text-xs text-ink-3">{s.note}</div>}
                {s.source_url && (
                  <a className="mt-1 inline-block text-xs text-accent underline" href={s.source_url} target="_blank" rel="noreferrer">
                    Odpri vir ↗
                  </a>
                )}
                <div className="mt-1 font-mono text-[11px] text-ink-3">{s.rule_id}</div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export function ExplainButton({ e, label = "Kako je izračunano?" }: { e: Explained; label?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button className="text-xs font-medium text-accent hover:underline" onClick={() => setOpen(true)}>
        ⓘ {label}
      </button>
      <Modal open={open} onClose={() => setOpen(false)} title={e.label}>
        <ExplainView e={e} />
      </Modal>
    </>
  );
}
