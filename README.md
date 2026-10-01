# HericR — osebni CFO + davčni nadzornik za s.p.

HericR spremlja tvoj s.p. sam: prihodke, stroške, prispevke, dohodnino, akontacijo in DDV.
Sproti išče napake, preverja pravila, napoveduje obveznosti in ti pove, kaj moraš narediti.
**Pri vsaki številki klikneš »ⓘ Kako je izračunano?«** in vidiš celotno pot do rezultata, skupaj z zakonom in virom.

> Načelo: **Claude je analitik, Tax Engine je kalkulator, FURS/PISRS so vir pravil, baza je vir tvojih podatkov.**
> AI nikoli sam ne računa davkov in si ne izmišljuje pravil. Kliče deterministični engine in rezultat razloži.

---

## Kaj je notri

| # | Funkcija | Kje |
|---|---|---|
| 1 | **Home**: 6 velikih številk (prihodki, stroški, davčna osnova, državi do sedaj, še dolguješ, realno ti ostane), napredek do cilja in pragov, opozorila | `/` |
| 2 | **AI nadzornik**: dnevni pregled ob 7:00 in klepet (»Če naredim še 20.000 €…?«) | `/ai` |
| 3 | **Tax Engine**: pravila v YAML z virom, veljavnostjo in statusom preverjenosti, razlaga vsakega koraka | `backend/app/tax_engine` |
| 4 | **What-if simulator**: normiranec in dejanski stroški pri različnih prihodkih, z grafom | `/whatif` |
| 5 | **Forecast**: LOW / CURRENT / HIGH / ciljni scenarij, za vsakega davki | `/napoved` |
| 6 | **Skener računov**: PDF ali fotografijo prebere AI, ti samo potrdiš »✅ Dodaj strošek« | `/stroski` |
| 7 | **Bančni uvoz**: camt.053 XML ali CSV, samodejna kategorizacija, povezava z računi in plačili FURS | `/banka` |
| 8 | **Find mistakes**: neplačani računi, plačila brez računov, dvojniki, napačen DDV, manjkajoči podatki, zasebni stroški, vrzeli v številčenju, zamujeni roki, pragovi | `/napake` |
| 9 | **Smart Tax Calendar**: roki z zneski, stanjem na TRR po plačilu in opozorilom glede varnostne rezerve | `/koledar` |
| 10 | **Tax Reserve**: koliko denarja mora ostati na računu za državo | `/rezerva` |
| 11 | **Profit vs Cash**: ustvarjeno nasproti dejansko prejetemu, odprte terjatve | `/rezerva` |
| 12 | **Explain** pri vsaki številki | povsod |
| 13 | **Document Vault** po letih in mapah, vsak dokument je povezljiv s transakcijo | `/dokumenti` |
| 14 | **Audit log**: vsaka sprememba (prej → potem) in vsak ponovni izračun | `/audit` |
| 15 | **Testni način**: zlati testi davčnega engina; ob spremembi pravil se poženejo sami | `/pravila` |
| 16 | **PWA**: računalnik, telefon, tablica, namestljiva kot aplikacija | |
| + | **Uvoz FURS dokumentov** (obračun DohDej, vloga DD-SprAkt): nastavi profil in preveri, da se engine ujema s FURS | `/dokumenti` |
| + | **Uvoz računov za nazaj iz Evelope** (eSLOG 2.0 XML, ZIP ovojnica s PDF-ji, Excel) in drugih programov (UBL/Peppol, CSV) | `/prihodki` |
| + | **Prijava z 2FA** (TOTP: Google Authenticator, Authy, 1Password) | `/nastavitve` |

---

## Hiter zagon

### A) Docker (priporočeno: PostgreSQL + MinIO za dokumente)

```bash
cp .env.example .env        # Windows: Copy-Item .env.example .env  → izpolni gesla
docker compose up -d --build
```

Odpri **http://localhost:3000**. Ob prvem obisku ustvariš lastniški račun.

Za telefon prek HTTPS (PWA namestitev): v `.env` nastavi `DOMAIN=tvoja.domena.si`, domena mora kazati na strežnik. Nato:

```bash
docker compose --profile https up -d
```

### B) Windows brez Dockerja (SQLite)

Namesti [Python 3.11+](https://www.python.org/downloads/) in [Node.js 22+](https://nodejs.org/), nato v PowerShellu:

```powershell
powershell -ExecutionPolicy Bypass -File .\start-windows.ps1
```

### C) Ročno (razvoj)

```bash
cd backend && python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/uvicorn app.main:app --reload --port 8000
cd frontend && npm ci && npm run dev        # http://localhost:3000
```

Demo podatki (sintetični) za preizkus:

```bash
HERICR_DATABASE_URL=sqlite:///./data/demo.db python -m scripts.demo_seed
# prijava: demo@hericr.si / demo-geslo-123
```

### AI (neobvezno)

V `.env` dodaj `ANTHROPIC_API_KEY` (pri Dockerju) oziroma `HERICR_ANTHROPIC_API_KEY` (pri zagonu brez Dockerja). Ključ dobiš na [console.anthropic.com](https://console.anthropic.com).
Brez ključa deluje vse razen AI klepeta, skenerja računov in AI besedila dnevnega pregleda. Številke dnevnega pregleda se izračunajo vseeno.
Uporabljen model je `claude-opus-5-5`, nastavljiv z `HERICR_AI_MODEL`. Vklopljen je samodejni rezervni model (server-side fallback).

---

## Prvi koraki

1. **Nastavitve** → 2FA (priporočeno, ker gre za finančne podatke).
2. **Dokumenti → ⚖️ Uvozi FURS dokument**: naloži zadnji obračun DohDej (DDD-DDD) in/ali vlogo DD-SprAkt iz eDavkov.
   HericR prebere režim, začetek dejavnosti, lanske prihodke in akontacijo. Nato **sam izračuna isto kot FURS in pokaže, ali se ujema**.
3. **Prihodki → ⬇️ Uvozi iz Evelope**: v Evelope izvozi račune kot e-račun XML ali ZIP ovojnico (lahko tudi Excel).
   Najprej vidiš predogled, nato potrdiš. Podvojeni računi se preskočijo, zato lahko uvoz ponoviš kadarkoli.
   Excel izvoz Evelope (»Št. računa, Partner, Datum storitve, Rok plačila, Znesek z DDV, Status«) nima datuma izdaje,
   datuma plačila in ločenega DDV. Zato izbereš **način DDV** (nezavezanec / obrnjena obveznost po 76.a / vključen DDV).
   Za datum izdaje se uporabi konec obdobja storitve, najkasneje rok plačila, za plačilo pa rok plačila.
   Točne datume plačil dobiš z uvozom bančnega izpiska. Dobropisi (»CR …«) se uvozijo z negativnim zneskom.
4. **Banka → Uvozi izpisek**: camt.053 XML iz spletne banke (NLB, OTP, SKB, Intesa …) ali CSV.
5. Preglej **Home**, **Koledar** in **Napake**.

---

## Davčna pravila 2026: kaj je notri in kako je preverjeno

Vsa pravila so v [`backend/app/tax_engine/rules/2026.yaml`](backend/app/tax_engine/rules/2026.yaml). Vsako ima vir, veljavnost in oznako `verified`.
Preverjeno **1. 10. 2026** v vsaj dveh neodvisnih virih (FURS, ZZZS, OZS, GZS, specializirani portali).

| Pravilo | Vrednost 2026 | Status |
|---|---|---|
| Lestvica dohodnine | 16 % do 9.721,43 · 26 % do 28.592,44 · 33 % do 57.184,88 · 39 % do 82.346,23 · 50 % nad | ✅ |
| Splošna olajšava | 5.551,93 € (+ dodatna do 17.766,18 € dohodka) | ✅ |
| Olajšave za otroke | 2.995,83 · 3.256,77 · 5.432,02 · +2.175,25 · posebna nega 10.856,24 | ✅ |
| **Normiranci (nova ureditev od 1. 1. 2026)** | polni (≥ 9 mes.): 80 % odhodkov do 60.000 €; davek 20 % do 72.000 € osnove, 35 % nad tem. Ostali: 80 % do 12.500 €, 40 % do 30.000 €; 20 % do 33.000 €, 35 % nad tem | ✅ |
| Vstop med normirance | povprečje 2 let ≤ 120.000 / 85.000 / 50.000 € | ✅ |
| Prispevki s.p. | 40,20 % (PIZ 24,35 · ZZ 13,45 · DO 2,00 · starševsko 0,20 · zaposlovanje 0,20) | ✅ |
| Najnižja / najvišja osnova | 1.521,62 € / 8.876,11 € (od feb. 2026) | ✅ |
| OZP | 37,17 € (jan–feb), 39,36 € (od marca 2026) | ✅ |
| Minimalni prispevki | **651,04 €** (od marca), **648,85 €** (februar). Engine se ujema z uradnim zneskom na cent | ✅ |
| Prva samozaposlitev | −50 % PIZ prvih 12 mesecev, −30 % naslednjih 12 | ✅ |
| DDV | 22 / 9,5 / 5 %, prag 60.000 € (takoj 66.000 €), novi zavezanec mesečno 12 mesecev | ✅ |
| Osnova za prispevke iz dobička | (dobiček + prispevki) × 75 % / 12 | ⚠️ preveri na odločbi |
| Rok mesečne akontacije | 20. v mesecu | ⚠️ viri se razlikujejo |
| **ZIURS** (interventni zakon) | sprejet, a **ne velja** (referendum). Samo kot simulacija v What-if | ⏳ |

**Preverba na pravih dokumentih FURS:** engine je bil preizkušen na pravem obračunu DohDej in vlogi DD-SprAkt.
Vseh 10 kontrolnih vrednosti se je ujemalo **na cent**: normirani odhodki, osnova, dohodnina, osnova za akontacijo ×12/6, akontacija in mesečni obrok.
Zneski iz teh dokumentov niso v repozitoriju (javen repo), v testih je isti mehanizem s sintetičnimi številkami.

### Ko se zakon spremeni

1. Uredi YAML (novo leto: `rules/2027.yaml`) in vpiši vir.
2. `cd backend && .venv/bin/pytest`. Zlati testi v `tests/test_tax_engine.py` in `tax_engine/golden.py` imajo ročno izračunana pričakovanja.
   Če formula ali pravilo spremeni rezultat, test pade, zato kalkulatorja nihče, tudi AI, ne more tiho pokvariti.
3. Ob zagonu aplikacija zazna spremembo pravil, sama požene zlate teste in rezultat zapiše v audit log (»❌ 3 TESTI FAILED«).

---

## Arhitektura

```
                    ┌───────────────┐
                    │  WEB / PWA    │  Next.js 16 · TypeScript · Tailwind 4
                    └───────┬───────┘
                            │ /api (isti izvor)
                    ┌───────▼───────┐
                    │  API SERVER   │  FastAPI · JWT + TOTP 2FA · audit log · dnevni scheduler
                    └───────┬───────┘
       ┌────────────────────┼────────────────────┐
       ▼                    ▼                    ▼
┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│ Tax Engine  │      │ Cash Engine │      │ AI Analyst  │  Claude (tool use → engine)
│ YAML pravila│      │ rezerva,    │      │ skener      │
│ + Explain   │      │ koledar,    │      │ računov     │
│ + zlati test│      │ napake      │      └─────────────┘
└──────┬──────┘      └──────┬──────┘             │
       └────────────────────┼────────────────────┘
                    ┌───────▼───────┐   ┌──────────────┐
                    │  PostgreSQL   │   │ S3 / MinIO   │ dokumenti
                    └───────────────┘   └──────────────┘
```

- `backend/app/tax_engine/`: `engine.py` (izračuni), `rules/*.yaml` (pravila), `trace.py` (Explain), `vat.py` (DDV obdobja), `workdays.py` (slovenski prazniki in roki), `golden.py` (testni način).
- `backend/app/engines/`: `ledger.py` (podatki), `dashboard.py`, `forecast.py`, `calendar.py`, `cash.py` (rezerva, profit vs cash), `mistakes.py`.
- `backend/app/integrations/`: `bank_import.py` (camt.053, CSV), `einvoice_import.py` (Evelope, eSLOG 2.0, UBL, Excel), `furs_import.py` (eDavki PDF), `invoice_scanner.py`, `ai_analyst.py`.
- Denar je vedno `Decimal`, zaokrožen na cent (half-up). Float se ne uporablja nikjer.

## Testi

```bash
cd backend && .venv/bin/pytest                       # 51 testov (SQLite)
HERICR_TEST_DATABASE_URL=postgresql+psycopg://user@host/db .venv/bin/pytest   # isto na PostgreSQL
cd frontend && npm run typecheck && npm run build
```

## Varnost

- Gesla: bcrypt. Seje: JWT. 2FA: TOTP. Registracija je zaprta po prvem (lastniškem) računu.
- `.env`, baza in dokumenti so v `.gitignore`. **Tvojih finančnih podatkov nikoli ne daj v repozitorij.**
  Repozitorij je trenutno **javen**, zato priporočam: GitHub → Settings → Change visibility → Private.
- Service worker nikoli ne shranjuje odgovorov `/api` v predpomnilnik.

## Omejitve (pošteno)

- HericR je orodje za pregled in planiranje, **ne nadomešča računovodje**. Pravila z oznako ⚠️ potrdi pri FURS ali računovodji.
- Dohodnina pri dejanskih stroških predpostavlja, da je s.p. tvoj edini dohodek.
- Evelope nima javnega API-ja, zato gre uvoz prek izvoza (XML/ZIP/Excel). Avtomatska sinhronizacija bi bila možna le, če Evelope ponudi API.
- Za leto 2025 so vnesena le pravila za normirance (za preverjanje obračuna). Celoten izračun za 2025 zato ni na voljo, računi in dokumenti pa so.
