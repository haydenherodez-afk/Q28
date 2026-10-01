"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, ReactNode, useContext, useEffect, useState } from "react";
import { api, getToken, setToken } from "@/lib/api";

const NAV: { href: string; label: string; icon: string; mobile?: boolean }[] = [
  { href: "/", label: "Home", icon: "🏠", mobile: true },
  { href: "/prihodki", label: "Prihodki", icon: "💰", mobile: true },
  { href: "/stroski", label: "Stroški", icon: "🧾", mobile: true },
  { href: "/koledar", label: "Koledar", icon: "📅", mobile: true },
  { href: "/ai", label: "AI analitik", icon: "🤖", mobile: true },
  { href: "/whatif", label: "What if?", icon: "🔄" },
  { href: "/napoved", label: "Napoved", icon: "🔮" },
  { href: "/rezerva", label: "Rezerva & Cash", icon: "🏦" },
  { href: "/banka", label: "Banka", icon: "💳" },
  { href: "/napake", label: "Napake", icon: "🕵️" },
  { href: "/dokumenti", label: "Dokumenti", icon: "🗂️" },
  { href: "/pravila", label: "Pravila & testi", icon: "⚖️" },
  { href: "/audit", label: "Audit log", icon: "🔐" },
  { href: "/nastavitve", label: "Nastavitve", icon: "⚙️" },
];

type Ctx = { year: number; setYear: (y: number) => void };
const YearCtx = createContext<Ctx>({ year: new Date().getFullYear(), setYear: () => {} });
export const useYear = () => useContext(YearCtx);

export default function AppShell({ children }: { children: ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const [year, setYearState] = useState(new Date().getFullYear());
  const [ready, setReady] = useState(false);
  const [menu, setMenu] = useState(false);
  const isLogin = path.startsWith("/login");

  useEffect(() => {
    try {
      const y = Number(localStorage.getItem("hericr.year"));
      if (y > 2000) setYearState(y);
    } catch { /* ignore */ }
    if (!isLogin && !getToken()) router.replace("/login");
    else setReady(true);
    if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
  }, [isLogin, router]);

  const setYear = (y: number) => {
    setYearState(y);
    try { localStorage.setItem("hericr.year", String(y)); } catch { /* ignore */ }
  };

  if (isLogin) return <>{children}</>;
  if (!ready) return null;

  const years = [2026, 2025].filter((y) => y <= new Date().getFullYear() + 1);
  const logout = () => { setToken(null); router.replace("/login"); };

  return (
    <YearCtx.Provider value={{ year, setYear }}>
      <div className="flex min-h-screen">
        <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-line bg-surface p-3 lg:flex">
          <Link href="/" className="mb-4 flex items-center gap-2 px-2 py-1">
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-accent text-lg font-black text-accent-ink">H</span>
            <span>
              <span className="block text-lg font-extrabold leading-none tracking-tight">HericR</span>
              <span className="text-[11px] text-ink-3">osebni CFO za s.p.</span>
            </span>
          </Link>
          <nav className="flex-1 space-y-0.5 overflow-y-auto">
            {NAV.map((n) => (
              <Link key={n.href} href={n.href}
                className={`flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm ${path === n.href ? "bg-surface-2 font-semibold" : "text-ink-2 hover:bg-surface-2"}`}>
                <span aria-hidden className="w-5 text-center">{n.icon}</span>{n.label}
              </Link>
            ))}
          </nav>
          <div className="mt-2 space-y-2 border-t border-line pt-3">
            <select className="field py-1.5 text-sm" value={year} onChange={(e) => setYear(Number(e.target.value))} aria-label="Leto">
              {years.map((y) => <option key={y} value={y}>Leto {y}</option>)}
            </select>
            <button className="btn w-full text-sm" onClick={logout}>Odjava</button>
          </div>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-30 flex items-center justify-between border-b border-line bg-surface/90 px-4 py-2.5 backdrop-blur lg:hidden">
            <Link href="/" className="flex items-center gap-2">
              <span className="grid h-8 w-8 place-items-center rounded-lg bg-accent font-black text-accent-ink">H</span>
              <span className="font-extrabold">HericR</span>
            </Link>
            <div className="flex items-center gap-2">
              <select className="field w-auto py-1 text-sm" value={year} onChange={(e) => setYear(Number(e.target.value))} aria-label="Leto">
                {years.map((y) => <option key={y} value={y}>{y}</option>)}
              </select>
              <button className="btn px-3 py-1.5" onClick={() => setMenu(true)} aria-label="Meni">☰</button>
            </div>
          </header>

          {menu && (
            <div className="fixed inset-0 z-50 bg-black/40 lg:hidden" onClick={() => setMenu(false)}>
              <nav className="card absolute right-0 top-0 h-full w-72 space-y-0.5 overflow-y-auto rounded-none p-3" onClick={(e) => e.stopPropagation()}>
                {NAV.map((n) => (
                  <Link key={n.href} href={n.href} onClick={() => setMenu(false)}
                    className={`flex items-center gap-2.5 rounded-lg px-3 py-2.5 ${path === n.href ? "bg-surface-2 font-semibold" : ""}`}>
                    <span aria-hidden>{n.icon}</span>{n.label}
                  </Link>
                ))}
                <button className="btn mt-3 w-full" onClick={logout}>Odjava</button>
              </nav>
            </div>
          )}

          <main className="mx-auto w-full max-w-7xl flex-1 px-4 pb-24 pt-5 sm:px-6 lg:pb-10">{children}</main>

          <nav className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-5 border-t border-line bg-surface/95 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden">
            {NAV.filter((n) => n.mobile).map((n) => (
              <Link key={n.href} href={n.href} className={`flex flex-col items-center py-2 text-[11px] ${path === n.href ? "font-semibold text-accent" : "text-ink-2"}`}>
                <span aria-hidden className="text-lg leading-none">{n.icon}</span>{n.label}
              </Link>
            ))}
          </nav>
        </div>
      </div>
    </YearCtx.Provider>
  );
}

export async function ping() {
  return api<{ ok: boolean }>("/health");
}
