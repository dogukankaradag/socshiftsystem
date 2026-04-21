import { NavLink, Outlet } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { ROLE_LABEL } from '../api/client';

const nav = [
  { to: '/', label: 'Panel' },
  { to: '/new', label: 'Yeni Giriş' },
  { to: '/incidents', label: 'Olaylar' },
  { to: '/reports', label: 'Raporlar' },
  { to: '/roster', label: 'Nöbetçi Listesi' },
  { to: '/analytics', label: 'Analitik' },
];

export default function Layout() {
  const { user, logout } = useAuth();
  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-white border-b border-gray-200 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center gap-6">
          <div className="font-semibold text-lg text-brand-700">Vardiya Devir Sistemi</div>
          <nav className="flex gap-1 flex-1">
            {nav.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.to === '/'}
                className={({ isActive }) =>
                  `px-3 py-1.5 rounded-md text-sm font-medium ${
                    isActive ? 'bg-brand-50 text-brand-700' : 'text-gray-600 hover:bg-gray-100'
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
                    isActive ? 'bg-brand-50 text-brand-700' : 'text-gray-600 hover:bg-gray-100'
                  }`
                }
              >
                Yönetim
              </NavLink>
            )}
          </nav>
          <div className="flex items-center gap-3 text-sm">
            <span className="text-gray-500">
              {user?.full_name}{' '}
              <span className="pill bg-gray-100 text-gray-700 ml-1">
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
      <footer className="text-center text-xs text-gray-400 py-4">
        Vardiya Devir Sistemi &middot; v0.4.0
      </footer>
    </div>
  );
}
