// Nöbetçi Listesi sayfası — v0.8.1: yalnızca L2 ekibi.
//
// MSSP aylık vardiyası artık "Aylık Vardiya Listesi" (otomasyon ile) sayfasında
// yönetiliyor; bu sayfada sadece L2 nöbet çizelgesi kaldı. Form/upload/tablo
// mantığı RosterListPage bileşeninden paylaşılır; XLSX/PDF yüklemeli toplu
// ekleme veya elle satır girişi aynı şekilde devam eder.
//
// Backend RosterTeam enum'unda hâlâ l2/mssp/distributor/lunch değerleri var
// (eski veriler korunur), ama bu sayfa yalnızca `l2` ekibini gösteriyor.
import RosterListPage from '../components/RosterListPage';

export default function Roster() {
  return (
    <RosterListPage
      teams={['l2']}
      pageTitle="Nöbetçi Listesi"
      pageSubtitle="L2 ekibi nöbet çizelgesi. XLSX/PDF yükleyerek toplu ekleyebilir veya elle satır girebilirsiniz."
    />
  );
}
