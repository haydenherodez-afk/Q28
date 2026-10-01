"""Uvozi FURS dokumente (obračun DohDej, vloga DD-SprAkt) in izvoze računov (Evelope Excel/XML/ZIP)
v obstoječo bazo HericR — za PRVEGA (lastniškega) uporabnika. Uporablja iste API klice kot aplikacija.

    cd backend
    .venv\\Scripts\\python -m scripts.uvozi_moje            (Windows; poišče datoteke v Prenosih, Namizju, Dokumentih)
    python -m scripts.uvozi_moje --mapa "C:\\pot\\do\\datotek" --ddv-2026 76a

--ddv-2025 / --ddv-2026: nezavezanec | 76a | vkljucen22   (način DDV za Excel izvoz brez ločenega DDV)
"""
import argparse
import os
import re
from pathlib import Path

os.environ.setdefault("HERICR_DATABASE_URL", "sqlite:///./data/hericr.db")
os.environ.setdefault("HERICR_STORAGE_DIR", "./data/files")
os.environ.setdefault("HERICR_SCHEDULER_ENABLED", "false")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.auth import create_token  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402


def najdi(mape: list[Path]) -> dict[str, list[Path]]:
    out = {"obracun": [], "sprakt": [], "racuni": []}
    for m in mape:
        if not m.exists():
            continue
        for p in m.rglob("*"):
            if not p.is_file() or p.stat().st_size > 60 * 1024 * 1024:
                continue
            n = p.name.lower()
            if n.endswith(".pdf") and "ddd_ddd" in n:
                out["obracun"].append(p)
            elif n.endswith(".pdf") and "sprakt" in n:
                out["sprakt"].append(p)
            elif re.match(r".*izvoz.*\.(xlsx|zip|xml)$", n):
                out["racuni"].append(p)
    for k in out:  # brez dvojnikov (ista datoteka v več mapah)
        seen, uniq = set(), []
        for p in sorted(out[k], key=lambda x: -x.stat().st_mtime):
            key = (p.name.split("-", 1)[-1] if re.match(r"^[0-9a-f]{8}-", p.name) else p.name, p.stat().st_size)
            if key not in seen:
                seen.add(key)
                uniq.append(p)
        out[k] = uniq
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mapa", action="append", help="mapa z datotekami (lahko večkrat)")
    ap.add_argument("--ddv-2025", default="nezavezanec")
    ap.add_argument("--ddv-2026", default="nezavezanec")
    ap.add_argument("--akontacija", default=None, help="letna akontacija, ki jo dejansko plačuješ (privzeto iz obračuna)")
    a = ap.parse_args()
    home = Path.home()
    mape = [Path(x) for x in a.mapa] if a.mapa else [home / "Downloads", home / "Prenosi", home / "Desktop",
                                                      home / "Namizje", home / "Documents", home / "Dokumenti",
                                                      home / "OneDrive"]
    init_db()
    db = SessionLocal()
    user = db.scalar(select(User).order_by(User.id))
    db.close()
    if user is None:
        raise SystemExit("V HericR še ni računa — najprej ga ustvari v brskalniku (http://localhost:3000).")
    h = {"Authorization": f"Bearer {create_token(user.id, minutes=30)}"}
    f = najdi(mape)
    print(f"Uporabnik: {user.email}")
    print(f"Najdeno: {len(f['obracun'])} obračun(ov), {len(f['sprakt'])} vlog(a), {len(f['racuni'])} izvoz(ov) računov")
    with TestClient(app) as c:
        upd = {}
        for p in f["obracun"][:1] + f["sprakt"][:1]:
            r = c.post("/api/furs/import", headers=h, files={"file": (p.name, p.read_bytes(), "application/pdf")})
            if r.status_code != 200:
                print(f"  ✗ {p.name}: {r.json().get('detail')}")
                continue
            d = r.json()
            ok = sum(x["match"] for x in d["checks"])
            print(f"  ✓ {d['document']['doc_type']} ({p.name}) — engine = FURS: {ok}/{len(d['checks'])}")
            if d["document"]["doc_type"] == "DDD-DDD":
                upd.update(d["profile_updates"])
            else:
                upd.update({k: v for k, v in d["profile_updates"].items() if k in ("business_name", "tax_number")})
        if a.akontacija:
            upd["akontacija_annual"] = a.akontacija
        upd["vat_registered"] = a.ddv_2026 != "nezavezanec"
        if upd["vat_registered"]:
            upd["vat_registration_date"] = "2026-01-01"
        r = c.post("/api/profile/apply", headers=h, json=upd)
        print("  ✓ profil nastavljen" if r.status_code == 200 else f"  ✗ profil: {r.text}")
        for p in f["racuni"]:
            data = p.read_bytes()
            pre = c.post("/api/import/invoices", headers=h, data={"dry_run": "true"}, files={"file": (p.name, data)}).json()
            years = sorted(pre.get("by_year", {}))
            mode = a.ddv_2026 if "2026" in years else a.ddv_2025
            r = c.post("/api/import/invoices", headers=h, data={"dry_run": "false", "vat_mode": mode},
                       files={"file": (p.name, data)})
            if r.status_code != 200:
                print(f"  ✗ {p.name}: {r.json().get('detail')}")
                continue
            d = r.json()
            print(f"  ✓ {p.name}: uvoženih {d['created_invoices']} računov, {d['skipped_duplicates']} že obstaja "
                  f"(DDV: {mode}) — " + ", ".join(f"{y}: {v['issued_net']} €" for y, v in sorted(d["by_year"].items())))
    print("Končano. Osveži stran v brskalniku.")


if __name__ == "__main__":
    main()
