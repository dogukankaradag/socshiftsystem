import { Navigate, Route, Routes } from 'react-router-dom';
import Layout from './components/Layout';
import ProtectedRoute from './components/ProtectedRoute';
import Admin from './pages/Admin';
import Analytics from './pages/Analytics';
import AylikVardiya from './pages/AylikVardiya';
import Customers from './pages/Customers';
import Dashboard from './pages/Dashboard';
import Distributors from './pages/Distributors';
import Incidents from './pages/Incidents';
import Login from './pages/Login';
import NewEntry from './pages/NewEntry';
import ReportDetail from './pages/ReportDetail';
import Reports from './pages/Reports';
import Roster from './pages/Roster';

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route path="/" element={<Dashboard />} />
        <Route path="/new" element={<NewEntry />} />
        <Route path="/incidents" element={<Incidents />} />
        <Route path="/reports" element={<Reports />} />
        <Route path="/reports/:id" element={<ReportDetail />} />
        <Route path="/roster" element={<Roster />} />
        <Route path="/distributors" element={<Distributors />} />
        {/* Aylık Vardiya Listesi — her giriş yapan kullanıcı görüntüleyebilir
            (read-only); düzenleme/Otomatik Üret butonları sayfa içinde
            rol kontrolüyle yalnızca Super Admin'e gösterilir. */}
        <Route path="/aylik-vardiya" element={<AylikVardiya />} />
        <Route path="/customers" element={<Customers />} />
        <Route path="/analytics" element={<Analytics />} />
        {/* Yönetim her iki rol için açık (Standart + Super Admin).
            Super Admin'e özel davranışlar Admin.tsx içinde rol kontrolü ile
            yapılır (örn. başka birini super_admin yapma). */}
        <Route
          path="/admin"
          element={
            <ProtectedRoute requireRole={['standard', 'super_admin']}>
              <Admin />
            </ProtectedRoute>
          }
        />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
