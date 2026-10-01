"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { api, setToken } from "@/lib/api";
import { Alert, Field } from "@/components/ui";

export default function Login() {
  const router = useRouter();
  const [needsSetup, setNeedsSetup] = useState<boolean | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [totp, setTotp] = useState("");
  const [askTotp, setAskTotp] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<{ needs_setup: boolean }>("/auth/status").then((r) => setNeedsSetup(r.needs_setup)).catch(() => setNeedsSetup(false));
  }, []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const path = needsSetup ? "/auth/setup" : "/auth/login";
      const r = await api<{ access_token: string | null; totp_required: boolean }>(path, {
        method: "POST", json: { email, password, ...(askTotp ? { totp } : {}) },
      });
      if (r.totp_required) { setAskTotp(true); return; }
      setToken(r.access_token);
      router.replace(needsSetup ? "/nastavitve?welcome=1" : "/");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-screen place-items-center px-4">
      <form onSubmit={submit} className="card w-full max-w-sm space-y-4 p-6">
        <div className="flex items-center gap-3">
          <span className="grid h-11 w-11 place-items-center rounded-xl bg-accent text-xl font-black text-accent-ink">H</span>
          <div>
            <h1 className="text-xl font-extrabold">HericR</h1>
            <p className="text-xs text-ink-2">osebni CFO + davčni nadzornik za s.p.</p>
          </div>
        </div>
        {needsSetup && <Alert kind="info">Prvi zagon: ustvari lastniški račun. Kasneje lahko vklopiš 2FA.</Alert>}
        <Field label="E-naslov"><input className="field" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
        <Field label="Geslo" hint={needsSetup ? "Najmanj 10 znakov." : undefined}>
          <input className="field" type="password" autoComplete={needsSetup ? "new-password" : "current-password"} required minLength={needsSetup ? 10 : 1} value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        {askTotp && (
          <Field label="2FA koda iz aplikacije">
            <input className="field num tracking-widest" inputMode="numeric" autoComplete="one-time-code" autoFocus required value={totp} onChange={(e) => setTotp(e.target.value)} />
          </Field>
        )}
        {error && <Alert kind="error">{error}</Alert>}
        <button className="btn btn-primary w-full" disabled={busy || needsSetup === null}>
          {busy ? "…" : needsSetup ? "Ustvari račun" : askTotp ? "Potrdi" : "Prijava"}
        </button>
      </form>
    </div>
  );
}
