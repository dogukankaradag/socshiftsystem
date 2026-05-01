// Nöbetçi Listesi sayfası — L2 Ekibi + MSSP aylık vardiya çizelgesi.
// Form/upload/tablo mantığı RosterListPage bileşeninde paylaşılır;
// Dağıtıcı Listesi sayfası da aynı bileşeni farklı `teams` ile kullanır.
import RosterListPage from '../components/RosterListPage';

export default function Roster() {
  return (
    <RosterListPage
      teams={['l2', 'mssp']}
      pageTitle="Nöbetçi Listesi"
      pageSubtitle="L2 ekibi ve MSSP aylık vardiya çizelgesi. XLSX/PDF yükleyerek toplu olarak ekleyebilir veya elle satır girebilirsiniz."
    />
  );
}
