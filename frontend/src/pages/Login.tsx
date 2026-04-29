import { FormEvent, useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';

export default function Login() {
  const { user, login, loading } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState('admin@example.com');
  const [password, setPassword] = useState('admin123');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (!loading && user) return <Navigate to="/" replace />;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
      nav('/');
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Giriş başarısız');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-brand-50 to-white dark:from-slate-900 dark:to-slate-800 px-4">
      <form onSubmit={onSubmit} className="card w-full max-w-sm space-y-4">
        <div>
          <h1 className="text-xl font-semibold text-gray-900 dark:text-slate-100">Vardiya Devir Sistemi</h1>
          <p className="text-sm text-gray-500 dark:text-slate-400">Devam etmek için giriş yapın</p>
        </div>
        <div>
          <label className="label">E-posta</label>
          <input
            type="email"
            className="input"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>
        <div>
          <label className="label">Parola</label>
          <input
            type="password"
            className="input"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </div>
        {error && <div className="text-sm text-red-600 dark:text-red-400">{error}</div>}
        <button type="submit" disabled={submitting} className="btn-primary w-full">
          {submitting ? 'Giriş yapılıyor…' : 'Giriş Yap'}
        </button>
        <p className="text-xs text-gray-400 dark:text-slate-500 text-center">
          Varsayılan: admin@example.com / admin123 — üretimde mutlaka değiştirin.
        </p>
      </form>
    </div>
  );
}
