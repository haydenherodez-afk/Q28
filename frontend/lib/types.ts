export type Step = { label: string; value: string | null; note: string };
export type Source = { rule_id: string; title: string; source: string; source_url: string | null; verified: boolean; note: string };
export type Explained = {
  key: string; label: string; value: string; formula: string; steps: Step[]; rule_ids: string[];
  warnings: string[]; sources?: Source[];
};
export type Card = Explained & { icon: string };
export type Progress = { key: string; label: string; value: string; max: string | null; ratio: number | null; note?: string };
export type Attention = { key: string; severity: "error" | "warning" | "info"; title: string; detail: string; code: string; entity: string | null };
export type Dashboard = {
  year: number; as_of: string; business_name: string; regime: string; scheme: string; cards: Card[];
  details: Record<string, Explained>; progress: Progress[]; attention: Attention[]; attention_minor: number; warnings: string[];
  daily_report: { day: string; ai_text: string | null; data: Record<string, unknown> } | null;
  rules_checked_on: string | null;
};
export type CalItem = {
  kind: string; title: string; period: string; due_date: string; amount: string | null; paid: string;
  status: "odprto" | "placano" | "zamujeno" | "ni_obveznosti"; explain: string; estimated?: boolean;
  days_until: number; balance_after?: string; cash_warning?: string; rule_ids: string[];
};
export type Finding = { severity: "error" | "warning" | "info"; code: string; key: string; title: string; detail: string; entity: string | null; entity_id: number | null };
export type Profile = {
  business_name: string; tax_number: string | null; iban: string | null; regime: "normiran" | "dejanski";
  full_time: boolean; activity_start: string; first_registration_date: string | null; vat_registered: boolean;
  vat_registration_date: string | null; prev_year_turnover: string; prev_year_insured_75: boolean; children: number;
  special_care_children: number; contribution_base_monthly: string | null; akontacija_annual: string;
  revenue_goal: string; safety_buffer: string;
};
export type Invoice = {
  id: number; number: string; customer: string; customer_tax_number: string | null; issue_date: string;
  service_date: string | null; due_date: string | null; net: string; vat_rate: string; vat: string; gross: string;
  vat_note: string | null; paid_date: string | null; paid_amount: string; notes: string | null; document_id: number | null;
};
export type Expense = {
  id: number; supplier: string; supplier_tax_number: string | null; invoice_number: string | null; date: string;
  net: string; vat: string; gross: string; vat_deductible: boolean; category: string | null; private_flag: boolean;
  paid_date: string | null; source: string; notes: string | null; document_id: number | null;
};
