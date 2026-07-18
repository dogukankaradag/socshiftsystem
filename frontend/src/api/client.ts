import axios from 'axios';

const baseURL = (import.meta.env.VITE_API_BASE_URL as string) || '/api';

export const api = axios.create({ baseURL, timeout: 30000 });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('shift_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (r) => r,
  (error) => {
    if (error.response?.status === 401 && !window.location.pathname.startsWith('/login')) {
      localStorage.removeItem('shift_token');
      localStorage.removeItem('shift_user');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  },
);

export async function downloadFile(path: string, filename: string) {
  const res = await api.get(path, { responseType: 'blob' });
  const url = window.URL.createObjectURL(new Blob([res.data]));
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}

// v0.6.2: 2 rollü sistem (standart / super_admin). Eski operator/supervisor/admin
// tipleri tamamen kaldırıldı; backend migration mevcut kullanıcıları standart'a
// çekiyor ve seed admin'i super_admin'e yükseltiyor.
export type Role = 'standard' | 'super_admin';
export type Priority = 'low' | 'medium' | 'high' | 'critical';
export type EntryType =
  | 'ddos_transfer'
  | 'info'
  | 'important_work'
  | 'l2_escalation'
  | 'callers'
  | 'dhs'
  | 'iys';
export type ShiftType = 'a' | 'b' | 'c';
export type IncidentStatus = 'open' | 'in_progress' | 'resolved' | 'closed';
export type ReportStatus = 'draft' | 'scheduled' | 'dispatched' | 'failed';

export const ENTRY_TYPE_LABEL: Record<EntryType, string> = {
  ddos_transfer: 'DDoS Taşıma',
  info: 'Bilgi',
  important_work: 'Yapılan Önemli İşler',
  l2_escalation: "L2'ye Eskale Edilen Konu",
  callers: 'Arayanlar',
  dhs: 'DHS',
  iys: 'İYS',
};

export const NUMERIC_ENTRY_TYPES: EntryType[] = ['dhs', 'iys'];

export const PRIORITY_LABEL: Record<Priority, string> = {
  low: 'düşük',
  medium: 'orta',
  high: 'yüksek',
  critical: 'kritik',
};

export const ROLE_LABEL: Record<Role, string> = {
  standard: 'Standart Kullanıcı',
  super_admin: 'Super Admin',
};

export const SHIFT_TYPE_LABEL: Record<ShiftType, string> = {
  a: 'A Vardiyası',
  b: 'B Vardiyası',
  c: 'C Vardiyası',
};

// Yerel saate göre (Europe/Istanbul, GMT+3) şu anki vardiyayı tahmin et.
// A: 07:30-15:30, B: 15:30-23:30, C: 23:30-07:30
export function detectShiftType(now: Date = new Date()): ShiftType {
  const tr = new Date(now.toLocaleString('en-US', { timeZone: 'Europe/Istanbul' }));
  const mins = tr.getHours() * 60 + tr.getMinutes();
  const a = 7 * 60 + 30;
  const b = 15 * 60 + 30;
  const c = 23 * 60 + 30;
  if (mins >= a && mins < b) return 'a';
  if (mins >= b && mins < c) return 'b';
  return 'c';
}

export const REPORT_STATUS_LABEL: Record<ReportStatus, string> = {
  draft: 'taslak',
  scheduled: 'zamanlandı',
  dispatched: 'gönderildi',
  failed: 'başarısız',
};

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  created_at: string;
}

export interface Shift {
  id: number;
  shift_type: ShiftType;
  started_at: string;
  ended_at: string | null;
  supervisor_id: number | null;
  notes: string | null;
  entry_count: number;
}

export interface Entry {
  id: number;
  shift_id: number;
  author_id: number;
  author_name?: string | null;
  entry_type: EntryType;
  title: string | null;
  body: string;
  numeric_value: number | null;
  occurs_at: string | null;
  reminder_sent_at: string | null;
  source: string | null;
  tags: string | null;
  incident_id: number | null;
  is_duplicate_of: number | null;
  // v0.6.1: "Arayanlar" snapshot alanları
  caller_org_name: string | null;
  caller_contact_name: string | null;
  caller_contact_phone: string | null;
  // v0.8.14: "DDoS Taşıma" MPLS ekibi + otomatik hatırlatma
  mpls_team_id: number | null;
  mpls_reminder_enabled: boolean;
  created_at: string;
  updated_at: string;
}

// v0.8.14: MPLS Ekipleri (DDoS Taşıma girişinde seçilir)
export interface MplsTeam {
  id: number;
  name: string;
  email: string;
  notes: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Incident {
  id: number;
  title: string;
  description: string;
  status: IncidentStatus;
  priority: Priority;
  opened_by_id: number;
  assigned_to_id: number | null;
  opened_at: string;
  resolved_at: string | null;
  resolution_notes: string | null;
  tags: string | null;
  entry_count: number;
}

export interface Report {
  id: number;
  shift_id: number;
  title: string;
  summary: string;
  body_markdown: string;
  body_html: string | null;
  status: ReportStatus;
  recipients: string | null;
  cc_recipients: string | null;
  scheduled_at: string | null;
  dispatched_at: string | null;
  error_message: string | null;
  created_at: string;
}

export interface TypeTotal {
  entry_type: EntryType;
  count: number;
  total: number;
}

export interface CallerStat {
  user_id: number;
  user_name: string;
  count: number;
}

export interface AnalyticsOverview {
  total_entries: number;
  open_incidents: number;
  upcoming_count: number;
  entries_by_type: { entry_type: EntryType; count: number }[];
  trend_14d: { date: string; total: number }[];
  totals_30d: TypeTotal[];
  top_tags: { tag: string; count: number }[];
  recurring_titles: { title: string; count: number }[];
  // v0.6.1: "Arayanlar" girişlerinin son 30 günlük kullanıcı dağılımı
  callers_by_user_30d?: CallerStat[];
}

// Roster (Nöbetçi Listesi) + Distributor (Dağıtıcı Listesi)
// l2 / mssp        → Nöbetçi Listesi sayfasında listelenir
// distributor / lunch → Dağıtıcı Listesi sayfasında listelenir
export type RosterTeam = 'l2' | 'mssp' | 'distributor' | 'lunch';

export const ROSTER_TEAM_LABEL: Record<RosterTeam, string> = {
  l2: 'L2 Ekibi',
  mssp: 'MSSP Vardiyaları',
  distributor: 'Aylık Dağıtıcı',
  lunch: 'Öğlen Nöbetçileri',
};

// Hangi takımlar için "Vardiya/Etiket" kolonu (shift_label) gösterilsin.
// MSSP için A/B/C, öğlen nöbeti için 12:00 / 13:00 gibi bir slot etiketi olabilir.
export const ROSTER_TEAMS_WITH_SHIFT_LABEL: Set<RosterTeam> = new Set([
  'mssp',
  'lunch',
]);

export interface RosterEntry {
  id: number;
  team: RosterTeam;
  person_name: string;
  start_date: string; // YYYY-MM-DD
  end_date: string;   // YYYY-MM-DD
  shift_label: string | null;
  notes: string | null;
  upload_batch: string | null;
  uploaded_by_id: number | null;
  uploaded_at: string;
}

export interface RosterUploadResult {
  upload_batch: string;
  parsed_count: number;
  team: RosterTeam;
  warnings: string[];
}

// v0.7.0: Aylık vardiya jeneratörü
export type PersonnelLocation = 'istanbul' | 'ankara';
export type PersonnelGroup = 'fixed_a' | 'istanbul' | 'ankara';
export type MonthlyShiftSlot =
  | 'a_fixed'
  | 'a_ankara'
  | 'a_istanbul'
  | 'b_shift'
  | 'c_shift'
  | 'oncall'
  | 'leave'
  | 'off'
  | 'wfh';

export const SLOT_LABEL: Record<MonthlyShiftSlot, string> = {
  a_fixed: 'A (Sabit)',
  a_ankara: 'A (Ank)',
  a_istanbul: 'A (İst)',
  b_shift: 'B',
  c_shift: 'C',
  oncall: 'On-Call',
  leave: 'İzin',
  off: 'Off',
  wfh: 'Evden Çalışma',
};

export const SLOT_SHORT: Record<MonthlyShiftSlot, string> = {
  a_fixed: 'A*',
  a_ankara: 'A',
  a_istanbul: 'A',
  b_shift: 'B',
  c_shift: 'C',
  oncall: 'ON',
  leave: 'İZ',
  off: 'Off',
  wfh: 'EV',
};

// Slot bazlı CSS rengi (Tailwind class'larıyla uyumlu).
// v0.8.0: 'leave' (izinli) artık belirgin kırmızı + kalın border — kullanıcı
// talebi: izinli kişiler hızlıca göze çarpsın.
export const SLOT_BG: Record<MonthlyShiftSlot, string> = {
  a_fixed: 'bg-yellow-100 text-yellow-900 dark:bg-yellow-900/30 dark:text-yellow-200',
  a_ankara: 'bg-amber-50 text-amber-900 dark:bg-amber-900/20 dark:text-amber-200',
  a_istanbul: 'bg-amber-50 text-amber-900 dark:bg-amber-900/20 dark:text-amber-200',
  b_shift: 'bg-orange-200 text-orange-900 dark:bg-orange-900/40 dark:text-orange-100',
  c_shift: 'bg-orange-300 text-orange-950 dark:bg-orange-800/60 dark:text-orange-50',
  oncall: 'bg-blue-200 text-blue-900 dark:bg-blue-900/40 dark:text-blue-100',
  leave: 'bg-red-200 text-red-900 font-bold border-2 border-red-600 dark:bg-red-900/50 dark:text-red-100 dark:border-red-400',
  off: 'bg-gray-100 text-gray-400 dark:bg-slate-800 dark:text-slate-500',
  // v0.8.6: EV (Evden Çalışma) — yumuşak mor/lila tonu, normal olduğunu
  // ama uzaktan olduğunu belirtmek için. Manuel atama; jeneratör üretmez.
  wfh: 'bg-purple-100 text-purple-900 italic dark:bg-purple-900/40 dark:text-purple-100',
};

export const LOCATION_LABEL: Record<PersonnelLocation, string> = {
  istanbul: 'İstanbul',
  ankara: 'Ankara',
};

export const GROUP_LABEL: Record<PersonnelGroup, string> = {
  fixed_a: 'Sabit A',
  istanbul: 'İstanbul',
  ankara: 'Ankara',
};

export interface Personnel {
  id: number;
  full_name: string;
  location: PersonnelLocation;
  group: PersonnelGroup;
  is_oncall_only: boolean;
  is_fixed_a: boolean;
  is_active: boolean;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface MonthlyShiftAssignment {
  id: number;
  personnel_id: number;
  personnel_name: string | null;
  day: string; // YYYY-MM-DD
  slot: MonthlyShiftSlot;
  modified_by_user_id: number | null;
  note: string | null;
  created_at: string;
  updated_at: string;
}

export interface GenerateMonthlyShiftResult {
  year: number;
  month: number;
  days_generated: number;
  assignments_created: number;
  assignments_preserved: number;
  warnings: string[];
}

// v0.8.1: Dağıtıcı + Öğlen Nöbetçi günlük atama
export type DailyDutyType = 'distributor' | 'lunch';

export const DUTY_LABEL: Record<DailyDutyType, string> = {
  distributor: 'Aylık Dağıtıcı',
  lunch: 'Öğlen Nöbetçi',
};

export interface DailyDuty {
  id: number;
  day: string; // YYYY-MM-DD
  duty_type: DailyDutyType;
  personnel_id: number;
  personnel_name: string | null;
  modified_by_user_id: number | null;
  note: string | null;
  created_at: string;
  updated_at: string;
}

export interface GenerateDailyDutyResult {
  year: number;
  month: number;
  weekdays_generated: number;
  assignments_created: number;
  assignments_preserved: number;
  per_person_distributor: Record<string, number>;
  per_person_lunch: Record<string, number>;
  warnings: string[];
}

// v0.6.1: Müşteri İrtibat Listesi (Customer Orgs + Contacts)
export interface CustomerContact {
  id: number;
  org_id: number;
  name: string;
  phone: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface CustomerOrg {
  id: number;
  name: string;
  notes: string | null;
  contacts: CustomerContact[];
  created_at: string;
  updated_at: string;
}
