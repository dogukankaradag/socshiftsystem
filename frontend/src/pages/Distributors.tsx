// Dağıtıcı Listesi sayfası — Aylık dağıtıcı + Öğlen nöbetçileri.
// UI/davranış aynı RosterListPage bileşenini kullanır; sadece takım filtresi
// (`distributor`, `lunch`) ve başlık farklıdır. Aynı /roster endpoint'leri,
// aynı yükleme/parse akışı (.xlsx / .pdf), aynı RBAC.
import RosterListPage from '../components/RosterListPage';

export default function Distributors() {
  return (
    <RosterListPage
      teams={['distributor', 'lunch']}
      pageTitle="Dağıtıcı Listesi"
      pageSubtitle="Aylık dağıtıcı ve öğlen nöbetçileri çizelgesi. Format Nöbetçi Listesi ile aynıdır — XLSX/PDF yükleyerek toplu olarak ekleyebilir veya elle satır girebilirsiniz."
    />
  );
}
