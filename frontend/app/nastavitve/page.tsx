"use client";

import { QRCodeSVG } from "qrcode.react";
import { FormEvent, useEffect, useState } from "react";
import { Alert, ErrorBox, Field, PageHeader, Section, Spinner, useApi } from "@/components/ui";
import { api } from "@/lib/api";
import type { Profile } from "@/lib/types";

export default function Nastavitve() {
  const prof = useApi<Profile>("/profile");
  const me = useApi<{ email: string; totp_enabled: boolean }>("/auth/me");
  const [p, setP] = useState<Profile | null>(null);
  const [saved, setSaved] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [totp, setTotp] = useState<{ secret: string; otpauth_uri: string } | null>(null);
  const [code, setCode] = useState("");
  const [welcome, setWelcome] = useState(false);
  useEffect(() => { if (prof.data) setP(prof.data); }, [prof.data]);
  useEffect(() => { setWelcome(new URLSearchParams(location.search).has("welcome")); }, []);

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!p) return;
    setErr(null); setSaved(false);
    try {
      const body = { ...p, contribution_base_monthly: p.contribution_base_monthly || null, first_registration_date: p.first_registration_date || null, vat_registration_date: p.vat_registration_date || null };
      setP(await api<Profile>("/profile", { method: "PUT", json: body }));
      setSaved(true);
    } catch (e) { setErr((e as Error).message); }
  }
  async function start2fa() { setTotp(await api("/auth/2fa/setup", { method: "POST" })); }
  async function enable2fa() {
    setErr(null);
    try { await api("/auth/2fa/enable", { method: "POST", json: { code } }); setTotp(null); setCode(""); me.reload(); }
    catch (e) { setErr((e as Error).message); }
  }
  async function disable2fa() {
    const c = prompt("Za izklop vpiši trenutno 2FA kodo");
    if (!c) return;
    try { await api("/auth/2fa/disable", { method: "POST", json: { code: c } }); me.reload(); } catch (e) { setErr((e as Error).message); }
  }

  const set = <K extends keyof Profile>(k: K, v: Profile[K]) => p && setP({ ...p, [k]: v });

  return (
    <div>
      <PageHeader title="⚙️ Nastavitve" />
      {welcome && <div className="mb-4"><Alert kind="info">Dobrodošel! Vnesi podatke o s.p. — ali pa v <a className="underline" href="/dokumenti">Dokumentih</a> uvozi zadnji obračun ali vlogo iz eDavkov in HericR jih izpolni sam.</Alert></div>}
      <ErrorBox error={prof.error} />
      <div className="grid gap-5 lg:grid-cols-3">
        <Section title="Podjetje in davčni status" className="lg:col-span-2">
          {!p ? <Spinner /> : (
            <form onSubmit={save} className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="sm:col-span-2"><Field label="Naziv s.p."><input className="field" value={p.business_name} onChange={(e) => set("business_name", e.target.value)} /></Field></div>
              <Field label="Davčna številka"><input className="field" value={p.tax_number ?? ""} onChange={(e) => set("tax_number", e.target.value)} /></Field>
              <Field label="IBAN (TRR)"><input className="field" value={p.iban ?? ""} onChange={(e) => set("iban", e.target.value)} /></Field>
              <Field label="Način ugotavljanja davčne osnove">
                <select className="field" value={p.regime} onChange={(e) => set("regime", e.target.value as Profile["regime"])}>
                  <option value="normiran">Normirani odhodki (normiranec)</option><option value="dejanski">Dejanski stroški</option>
                </select>
              </Field>
              <Field label="Vrsta s.p.">
                <select className="field" value={p.full_time ? "1" : "0"} onChange={(e) => set("full_time", e.target.value === "1")}>
                  <option value="1">Polni (zavarovan za polni delovni čas)</option><option value="0">Popoldanski</option>
                </select>
              </Field>
              <Field label="Začetek dejavnosti"><input className="field" type="date" value={p.activity_start} onChange={(e) => set("activity_start", e.target.value)} /></Field>
              <Field label="Prvi vpis v poslovni register" hint="Samo če je to tvoj PRVI s.p. (50 % / 30 % olajšava PIZ). Sicer pusti prazno.">
                <input className="field" type="date" value={p.first_registration_date ?? ""} onChange={(e) => set("first_registration_date", e.target.value || null)} />
              </Field>
              <Field label="Zavezanec za DDV">
                <select className="field" value={p.vat_registered ? "1" : "0"} onChange={(e) => set("vat_registered", e.target.value === "1")}>
                  <option value="1">Da</option><option value="0">Ne</option>
                </select>
              </Field>
              <Field label="ID za DDV od"><input className="field" type="date" value={p.vat_registration_date ?? ""} onChange={(e) => set("vat_registration_date", e.target.value || null)} /></Field>
              <Field label="Prihodki preteklega leta (€)" hint="Za prag normirancev (povprečje 2 let) in DDV."><input className="field num" value={p.prev_year_turnover} onChange={(e) => set("prev_year_turnover", e.target.value)} /></Field>
              <Field label="Lani polno zavarovan ≥ 75 % leta?">
                <select className="field" value={p.prev_year_insured_75 ? "1" : "0"} onChange={(e) => set("prev_year_insured_75", e.target.value === "1")}>
                  <option value="1">Da</option><option value="0">Ne</option>
                </select>
              </Field>
              <Field label="Letna akontacija dohodnine (€)" hint="Iz zadnjega obračuna ali odobrene vloge DD-SprAkt."><input className="field num" value={p.akontacija_annual} onChange={(e) => set("akontacija_annual", e.target.value)} /></Field>
              <Field label="Zavarovalna osnova (€/mesec)" hint="Prazno = najnižja osnova (1.521,62 €)."><input className="field num" value={p.contribution_base_monthly ?? ""} onChange={(e) => set("contribution_base_monthly", e.target.value || null)} /></Field>
              <Field label="Vzdrževani otroci"><input className="field num" type="number" min={0} value={p.children} onChange={(e) => set("children", Number(e.target.value))} /></Field>
              <Field label="Otroci, ki potrebujejo posebno nego"><input className="field num" type="number" min={0} value={p.special_care_children} onChange={(e) => set("special_care_children", Number(e.target.value))} /></Field>
              <Field label="Letni cilj prihodkov (€)"><input className="field num" value={p.revenue_goal} onChange={(e) => set("revenue_goal", e.target.value)} /></Field>
              <Field label="Varnostna rezerva na TRR (€)"><input className="field num" value={p.safety_buffer} onChange={(e) => set("safety_buffer", e.target.value)} /></Field>
              {err && <div className="sm:col-span-2"><Alert kind="error">{err}</Alert></div>}
              {saved && <div className="sm:col-span-2"><Alert kind="good">Shranjeno. Vsi izračuni so posodobljeni.</Alert></div>}
              <div className="sm:col-span-2"><button className="btn btn-primary">Shrani</button></div>
            </form>
          )}
        </Section>
        <Section title="🔐 Varnost — 2FA">
          {!me.data ? <Spinner /> : (
            <div className="space-y-3 text-sm">
              <div>Prijavljen kot <b>{me.data.email}</b></div>
              {me.data.totp_enabled ? (
                <><Alert kind="good">Dvostopenjska prijava je vklopljena.</Alert><button className="btn btn-danger" onClick={disable2fa}>Izklopi 2FA</button></>
              ) : totp ? (
                <div className="space-y-3">
                  <p>Skeniraj kodo z Google Authenticator, Authy ali 1Password:</p>
                  <div className="inline-block rounded-xl bg-white p-3"><QRCodeSVG value={totp.otpauth_uri} size={168} /></div>
                  <p className="break-all font-mono text-xs text-ink-3">{totp.secret}</p>
                  <Field label="Koda iz aplikacije"><input className="field num tracking-widest" inputMode="numeric" value={code} onChange={(e) => setCode(e.target.value)} /></Field>
                  <button className="btn btn-primary" onClick={enable2fa}>Vklopi 2FA</button>
                </div>
              ) : (
                <><Alert kind="warning">2FA ni vklopljena. Ker aplikacija hrani finančne podatke, jo vklopi.</Alert><button className="btn btn-primary" onClick={start2fa}>Nastavi 2FA</button></>
              )}
            </div>
          )}
        </Section>
      </div>
    </div>
  );
}
