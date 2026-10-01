const eurFmt = new Intl.NumberFormat("sl-SI", { style: "currency", currency: "EUR", minimumFractionDigits: 2 });
const eur0Fmt = new Intl.NumberFormat("sl-SI", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });

export const toNum = (v: string | number | null | undefined) => (v === null || v === undefined || v === "" ? 0 : Number(v));
export const eur = (v: string | number | null | undefined) => (v === null || v === undefined ? "—" : eurFmt.format(toNum(v)));
export const eur0 = (v: string | number | null | undefined) => (v === null || v === undefined ? "—" : eur0Fmt.format(toNum(v)));
export const pct = (r: number) => `${(r * 100).toLocaleString("sl-SI", { maximumFractionDigits: 1 })} %`;
export const dateSl = (iso?: string | null) => {
  if (!iso) return "—";
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${Number(d)}. ${Number(m)}. ${y}`;
};
export const MONTHS = ["jan", "feb", "mar", "apr", "maj", "jun", "jul", "avg", "sep", "okt", "nov", "dec"];

/** Slovenska dvojina/množina: čez 1 dan, 2 dneva, 3 dni; pred 1 dnem, 2 dnevoma, 3 dnevi. */
export const inDays = (n: number) => (n === 1 ? "čez 1 dan" : n === 2 ? "čez 2 dneva" : `čez ${n} dni`);
export const agoDays = (n: number) => (n === 1 ? "pred 1 dnem" : n === 2 ? "pred 2 dnevoma" : `pred ${n} dnevi`);
export const lateDays = (n: number) => (n === 1 ? "1 dan" : n === 2 ? "2 dneva" : `${n} dni`);
