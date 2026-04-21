import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { api, downloadFile, REPORT_STATUS_LABEL, Report } from '../api/client';

export default function ReportDetail() {
  const { id } = useParams<{ id: string }>();
  const nav = useNavigate();
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get(`/reports/${id}`)
      .then((r) => setReport(r.data))
      .catch((e) => setError(e?.response?.data?.detail || 'Rapor bulunamadı'));
  }, [id]);

  if (error) return <div className="text-red-600">{error}</div>;
  if (!report) return <div className="text-gray-500">Yükleniyor...</div>;

  return (
    <div className="space-y-4">
      <button className="btn-ghost text-sm" onClick={() => nav(-1)}>
        Geri
      </button>
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">{report.title}</h1>
        <button
          className="btn-primary"
          onClick={() =>
            downloadFile(`/reports/${report.id}/export.pdf`, `rapor_${report.id}.pdf`)
          }
        >
          PDF İndir
        </button>
      </div>
      <div className="text-sm text-gray-500 space-y-1">
        <div>
          Durum: <b>{REPORT_STATUS_LABEL[report.status]}</b>
        </div>
        {report.scheduled_at && (
          <div>
            Planlanan gönderim: {new Date(report.scheduled_at).toLocaleString('tr-TR')} (GMT+3)
          </div>
        )}
        {report.dispatched_at && (
          <div>Gönderildi: {new Date(report.dispatched_at).toLocaleString('tr-TR')}</div>
        )}
        {report.recipients && <div>TO: {report.recipients}</div>}
        {report.cc_recipients && <div>CC: {report.cc_recipients}</div>}
        {report.error_message && (
          <div className="text-red-600">Hata: {report.error_message}</div>
        )}
      </div>
      <div className="card">
        <h2 className="font-semibold text-gray-900 mb-2">Yönetici Özeti</h2>
        <p className="text-gray-800 whitespace-pre-wrap">{report.summary}</p>
      </div>
      <div className="card">
        <h2 className="font-semibold text-gray-900 mb-2">Hazırlanan Rapor</h2>
        {report.body_html ? (
          <iframe
            title="rapor"
            srcDoc={report.body_html}
            className="w-full min-h-[500px] border border-gray-200 rounded-md bg-white"
          />
        ) : (
          <pre className="whitespace-pre-wrap text-sm text-gray-800">{report.body_markdown}</pre>
        )}
      </div>
    </div>
  );
}
