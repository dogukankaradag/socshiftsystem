import { NavLink, Outlet } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { ROLE_LABEL } from '../api/client';
import { useTheme } from '../theme/ThemeContext';

const nav = [
  { to: '/', label: 'Panel' },
  { to: '/new', label: 'Yeni Giriş' },
  { to: '/incidents', label: 'Olaylar' },
  { to: '/reports', label: 'Raporlar' },
  { to: '/roster', label: 'Nöbetçi Listesi' },
  { to: '/analytics', label: 'Analitik' },
];

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
            Vardiya Devir Sistemi
          </div>
          <nav className="flex gap-1 flex-1">
            {nav.map((n) => (
              <NavLink
                key={n.to}
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
            ))}
            {user?.role === 'admin' && (
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
        Vardiya Devir Sistemi &middot; v0.5.2
      </footer>
    </div>
  );
}
