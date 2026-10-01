"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { useYear } from "@/components/AppShell";
import { Alert, PageHeader, useApi } from "@/components/ui";
import { api } from "@/lib/api";

type Msg = { role: "user" | "assistant"; text: string; tools?: string[] };
const EXAMPLES = [
  "Če letos naredim še 20.000 € prihodkov, koliko približno mi ostane in katere obveznosti se spremenijo?",
  "Koliko moram imeti na računu za davke do konca leta?",
  "Ali mi bolj splača normiranec ali dejanski stroški pri 90.000 €?",
  "Kateri rok je naslednji in ali imam dovolj denarja?",
  "Kaj je narobe v mojih podatkih?",
];

export default function AI() {
  const { year } = useYear();
  const status = useApi<{ enabled: boolean; model: string }>("/ai/status");
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [conv, setConv] = useState<number | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => end.current?.scrollIntoView({ behavior: "smooth" }), [msgs, busy]);

  async function send(q: string) {
    if (!q.trim() || busy) return;
    setErr(null); setBusy(true); setText("");
    setMsgs((m) => [...m, { role: "user", text: q }]);
    try {
      const r = await api<{ conversation_id: number; answer: string; tools_used: string[] }>(`/ai/chat?year=${year}`, { method: "POST", json: { message: q, conversation_id: conv } });
      setConv(r.conversation_id);
      setMsgs((m) => [...m, { role: "assistant", text: r.answer, tools: r.tools_used }]);
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  }
  const submit = (e: FormEvent) => { e.preventDefault(); send(text); };

  return (
    <div className="flex h-[calc(100vh-9rem)] flex-col lg:h-[calc(100vh-4rem)]">
      <PageHeader title="🤖 AI analitik" subtitle="Claude vzame podatke iz baze → davčni engine naredi izračun → Claude rezultat razloži. Davkov si ne izmišljuje."
        actions={msgs.length > 0 && <button className="btn" onClick={() => { setMsgs([]); setConv(null); }}>Nov pogovor</button>} />
      {status.data && !status.data.enabled && <div className="mb-3"><Alert kind="warning">AI ni nastavljen. V datoteko <code>.env</code> dodaj <code>HERICR_ANTHROPIC_API_KEY</code> in ponovno zaženi backend. Vse ostale funkcije delujejo brez AI.</Alert></div>}
      <div className="card flex-1 space-y-4 overflow-y-auto p-4">
        {msgs.length === 0 && (
          <div className="space-y-2">
            <p className="text-sm text-ink-2">Primeri vprašanj:</p>
            {EXAMPLES.map((q) => <button key={q} className="block w-full rounded-xl border border-line px-3 py-2 text-left text-sm hover:bg-surface-2" onClick={() => send(q)}>{q}</button>)}
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            <div className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-sm ${m.role === "user" ? "bg-accent text-accent-ink" : "bg-surface-2"}`}>
              {m.text}
              {m.tools && m.tools.length > 0 && <div className="mt-2 text-[11px] text-ink-3">🧮 uporabljen engine: {Array.from(new Set(m.tools)).join(", ")}</div>}
            </div>
          </div>
        ))}
        {busy && <div className="text-sm text-ink-2">Analiziram in računam z davčnim enginom…</div>}
        {err && <Alert kind="error">{err}</Alert>}
        <div ref={end} />
      </div>
      <form onSubmit={submit} className="mt-3 flex gap-2">
        <input className="field" placeholder="Vprašaj svojo stran…" value={text} onChange={(e) => setText(e.target.value)} disabled={busy} />
        <button className="btn btn-primary" disabled={busy || !text.trim()}>Pošlji</button>
      </form>
    </div>
  );
}
