import { useEffect, useRef, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { ROLE_LABEL } from '../api/client';
import { useTheme } from '../theme/ThemeContext';

// Üst menüde "Nöbetçi Listesi" başlığı bir dropdown'a dönüştü; alt
// kalemleri olarak hem L2/MSSP nöbetçileri hem de aylık dağıtıcı/öğlen
// nöbetçileri listesi yer alır. Diğer linkler düz kalır.
const nav = [
  { to: '/', label: 'Panel' },
  { to: '/new', label: 'Yeni Giriş' },
  { to: '/incidents', label: 'Olaylar' },
  { to: '/reports', label: 'Raporlar' },
  { to: '/customers', label: 'Müşteri İrtibat Listesi' },
  { to: '/analytics', label: 'Analitik' },
];

// v0.6.3 / v0.7.2: Üst menüdeki dropdown başlığı "Vardiya Listesi".
// Alt kalemlerin tümü her giriş yapan kullanıcıya görünür; düzenleme
// yetkisi sayfa içinde rol kontrolüyle yapılır:
//   - Nöbetçi Listesi (L2 + MSSP) — herkes okur, super_admin düzenler
//   - Dağıtıcı Listesi (Aylık Dağıtıcı + Öğlen Nöbetçileri) — aynı yetki
//   - Aylık Vardiya Listesi — herkes okur (read-only), super_admin
//                              Otomatik Üret / hücre düzenleme yapabilir.
interface RosterMenuItem {
  to: string;
  label: string;
  superAdminOnly?: boolean;
}

const rosterMenu: RosterMenuItem[] = [
  { to: '/roster', label: 'Nöbetçi Listesi' },
  { to: '/distributors', label: 'Dağıtıcı Listesi' },
  { to: '/aylik-vardiya', label: 'Aylık Vardiya Listesi' },
];

function RosterMenu() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const location = useLocation();
  const navigate = useNavigate();
  const { user } = useAuth();

  // Kullanıcı rolüne göre görünür alt kalemler.
  const visibleItems = rosterMenu.filter(
    (m) => !m.superAdminOnly || user?.role === 'super_admin',
  );
  const isActive = visibleItems.some((m) => location.pathname.startsWith(m.to));

  // Sayfa değiştiğinde dropdown'u kapat.
  useEffect(() => {
    setOpen(false);
  }, [location.pathname]);

  // Dışarı tıklayınca kapat.
  useEffect(() => {
    if (!open) return;
    function onDoc(ev: MouseEvent) {
      if (ref.current && !ref.current.contains(ev.target as Node)) {
        setOpen(false);
      }
    }
    function onKey(ev: KeyboardEvent) {
      if (ev.key === 'Escape') setOpen(false);
    }
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        className={`px-3 py-1.5 rounded-md text-sm font-medium inline-flex items-center gap-1 ${
          isActive
            ? 'bg-brand-50 text-brand-700 dark:bg-slate-700 dark:text-brand-400'
            : 'text-gray-600 hover:bg-gray-100 dark:text-slate-300 dark:hover:bg-slate-700'
        }`}
      >
        Vardiya Listesi
        <svg
          viewBox="0 0 20 20"
          width="12"
          height="12"
          fill="currentColor"
          className={`transition-transform ${open ? 'rotate-180' : ''}`}
          aria-hidden="true"
        >
          <path d="M5.23 7.21a.75.75 0 011.06.02L10 11.06l3.71-3.83a.75.75 0 111.08 1.04l-4.25 4.39a.75.75 0 01-1.08 0L5.21 8.27a.75.75 0 01.02-1.06z" />
        </svg>
      </button>

      {open && (
        <div
          role="menu"
          className="absolute left-0 mt-1 min-w-[220px] rounded-md border border-gray-200 bg-white shadow-lg
                     dark:border-slate-700 dark:bg-slate-800 z-30 py-1"
        >
          {visibleItems.map((m) => {
            const active = location.pathname === m.to;
            return (
              <button
                key={m.to}
                type="button"
                role="menuitem"
                onClick={() => {
                  setOpen(false);
                  navigate(m.to);
                }}
                className={`w-full text-left px-3 py-1.5 text-sm ${
                  active
                    ? 'bg-brand-50 text-brand-700 dark:bg-slate-700 dark:text-brand-400'
                    : 'text-gray-700 hover:bg-gray-100 dark:text-slate-200 dark:hover:bg-slate-700'
                }`}
              >
                {m.label}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function ThemeToggle() {
  const { theme, toggle } = useTheme();
  const isDark = theme === 'dark';
  return (
    <button
      type="button"
      onClick={toggle}
      title={isDark ? 'Aydınlık temaya geç' : 'Karanlık temaya geç'}
      aria-label="Tema değiştir"
      className="inline-flex items-center justify-center w-9 h-9 rounded-md
                 text-gray-600 hover:bg-gray-100
                 dark:text-slate-300 dark:hover:bg-slate-700 transition"
    >
      {isDark ? (
        // Sun icon — aydınlık moda dönüş
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
        </svg>
      ) : (
        // Moon icon — karanlık moda geç
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
        </svg>
      )}
    </button>
  );
}

export default function Layout() {
  const { user, logout } = useAuth();
  return (
    <div className="min-h-screen flex flex-col bg-gray-50 dark:bg-slate-900">
      <header className="bg-white border-b border-gray-200 shadow-sm dark:bg-slate-800 dark:border-slate-700">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center gap-6">
          <div className="font-semibold text-lg text-brand-700 dark:text-brand-400">
            MSSP Handover
          </div>
          <nav className="flex gap-1 flex-1 items-center">
            {nav.map((n) => (
              <span key={n.to} className="contents">
                <NavLink
                  to={n.to}
                  end={n.to === '/'}
                  className={({ isActive }) =>
                    `px-3 py-1.5 rounded-md text-sm font-medium ${
                      isActive
                        ? 'bg-brand-50 text-brand-700 dark:bg-slate-700 dark:text-brand-400'
                        : 'text-gray-600 hover:bg-gray-100 dark:text-slate-300 dark:hover:bg-slate-700'
                    }`
                  }
                >
                  {n.label}
                </NavLink>
                {/* Raporlar'dan hemen sonra Nöbetçi Listesi dropdown'ını araya ekliyoruz. */}
                {n.to === '/reports' && <RosterMenu />}
              </span>
            ))}
            {(user?.role === 'standard' || user?.role === 'super_admin') && (
              <NavLink
                to="/admin"
                className={({ isActive }) =>
                  `px-3 py-1.5 rounded-md text-sm font-medium ${
                    isActive
                      ? 'bg-brand-50 text-brand-700 dark:bg-slate-700 dark:text-brand-400'
                      : 'text-gray-600 hover:bg-gray-100 dark:text-slate-300 dark:hover:bg-slate-700'
                  }`
                }
              >
                Yönetim
              </NavLink>
            )}
          </nav>
          <div className="flex items-center gap-3 text-sm">
            <ThemeToggle />
            <span className="text-gray-500 dark:text-slate-400">
              {user?.full_name}{' '}
              <span className="pill bg-gray-100 text-gray-700 ml-1 dark:bg-slate-700 dark:text-slate-200">
                {user ? ROLE_LABEL[user.role] : ''}
              </span>
            </span>
            <button className="btn-ghost" onClick={logout}>
              Çıkış Yap
            </button>
          </div>
        </div>
      </header>
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 py-6">
        <Outlet />
      </main>
      <footer className="text-center text-xs text-gray-400 py-4 dark:text-slate-500">
        MSSP Handover &middot; v0.8.14
      </footer>
    </div>
  );
}
