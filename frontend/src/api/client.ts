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

export type Role = 'operator' | 'supervisor' | 'admin';
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
  operator: 'operatör',
  supervisor: 'süpervizör',
  admin: 'yönetici',
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

export interface AnalyticsOverview {
  total_entries: number;
  open_incidents: number;
  upcoming_count: number;
  entries_by_type: { entry_type: EntryType; count: number }[];
  trend_14d: { date: string; total: number }[];
  totals_30d: TypeTotal[];
  top_tags: { tag: string; count: number }[];
  recurring_titles: { title: string; count: number }[];
}

// Roster (Nöbetçi Listesi)
export type RosterTeam = 'l2' | 'mssp';

export const ROSTER_TEAM_LABEL: Record<RosterTeam, string> = {
  l2: 'L2 Ekibi',
  mssp: 'MSSP Vardiyaları',
};

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
