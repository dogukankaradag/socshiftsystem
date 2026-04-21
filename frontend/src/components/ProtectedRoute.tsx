import { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { Role } from '../api/client';

interface Props {
  children: ReactNode;
  requireRole?: Role[];
}

export default function ProtectedRoute({ children, requireRole }: Props) {
  const { user, token, loading } = useAuth();
  if (loading) {
    return <div className="flex items-center justify-center h-screen text-gray-500">Loading…</div>;
  }
  if (!token || !user) {
    return <Navigate to="/login" replace />;
  }
  if (requireRole && !requireRole.includes(user.role)) {
    return <Navigate to="/" replace />;
  }
  return <>{children}</>;
}
