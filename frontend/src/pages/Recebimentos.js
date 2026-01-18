import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Label } from '../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { toast } from 'sonner';
import { ArrowLeft, Scale, DollarSign, TrendingUp, FileText, Download } from 'lucide-react';
import { formatDateBR, formatCurrency } from '../utils/formatters';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export default function Recebimentos({ token, setToken }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [preset, setPreset] = useState('month');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [beneficiario, setBeneficiario] = useState('all');
  const [type, setType] = useState('all');
  const navigate = useNavigate();

  const fetchReceipts = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (preset !== 'custom') {
        params.append('preset', preset);
      } else {
        if (startDate) params.append('start_date', startDate);
        if (endDate) params.append('end_date', endDate);
      }
      if (beneficiario !== 'all') params.append('beneficiario', beneficiario);
      if (type !== 'all') params.append('type', type);

      const response = await axios.get(`${API}/receipts?${params.toString()}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setData(response.data);
    } catch (error) {
      if (error.response?.status === 401) {
        setToken(null);
        navigate('/login');
      } else {
        toast.error('Erro ao carregar recebimentos');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchReceipts();
  }, [preset, startDate, endDate, beneficiario, type]);

  const exportToCSV = () => {
    if (!data || !data.receipts || data.receipts.length === 0) {
      toast.error('Nenhum dado para exportar');
      return;
    }

    const headers = ['Data', 'Devedor', 'Nº Processo', 'Tipo', 'Valor', 'Beneficiário', 'Observações'];
    const rows = data.receipts.map(r => [
      formatDateBR(r.date),
      r.debtor,
      r.numero_processo || '',
      r.type,
      r.value.toFixed(2),
      r.beneficiario,
      r.observacoes || ''
    ]);

    const csvContent = [
      headers.join(','),
      ...rows.map(row => row.map(cell => `"${cell}"`).join(','))
    ].join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    link.setAttribute('href', url);
    link.setAttribute('download', `recebimentos_${new Date().toISOString().split('T')[0]}.csv`);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    toast.success('Arquivo CSV exportado com sucesso!');
  };

  if (loading && !data) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <p className="text-slate-600">Carregando...</p>
      </div>
    );
  }

  const chartData = data?.monthly_consolidation.map(m => ({
    month: m.month,
    '31': m.total_31,
    '14': m.total_14,
    Parcelas: m.total_parcelas,
    Alvarás: m.total_alvaras,
  })) || [];

  return (
    <div className="min-h-screen bg-slate-50">
      <nav className="bg-white border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center space-x-3 h-16">
            <Button
              onClick={() => navigate('/cases')}
              variant="ghost"
              className="hover:bg-slate-100"
              data-testid="back-button"
            >
              <ArrowLeft className="w-5 h-5 mr-2" />
              Voltar
            </Button>
            <div className="flex items-center space-x-3">
              <DollarSign className="w-8 h-8 text-emerald-600" />
              <h1 className="text-xl font-bold text-slate-900">Recebimentos</h1>
            </div>
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-6 mb-8">
          <h3 className="font-semibold text-slate-900 mb-4">Filtros</h3>
          <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
            <div>
              <Label htmlFor="preset">Período</Label>
              <Select value={preset} onValueChange={setPreset}>
                <SelectTrigger className="mt-1" data-testid="preset-select">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="day">Dia (Hoje)</SelectItem>
                  <SelectItem value="week">Semana</SelectItem>
                  <SelectItem value="month">Mês</SelectItem>
                  <SelectItem value="year">Ano</SelectItem>
                  <SelectItem value="custom">Personalizado</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {preset === 'custom' && (
              <>
                <div>
                  <Label htmlFor="startDate">Data inicial</Label>
                  <Input
                    id="startDate"
                    type="date"
                    value={startDate}
                    onChange={(e) => setStartDate(e.target.value)}
                    className="mt-1"
                    data-testid="start-date-input"
                  />
                </div>
                <div>
                  <Label htmlFor="endDate">Data final</Label>
                  <Input
                    id="endDate"
                    type="date"
                    value={endDate}
                    onChange={(e) => setEndDate(e.target.value)}
                    className="mt-1"
                    data-testid="end-date-input"
                  />
                </div>
              </>
            )}

            <div>
              <Label htmlFor="beneficiario">Beneficiário</Label>
              <Select value={beneficiario} onValueChange={setBeneficiario}>
                <SelectTrigger className="mt-1" data-testid="beneficiario-select">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Todos</SelectItem>
                  <SelectItem value="31">31</SelectItem>
                  <SelectItem value="14">14</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div>
              <Label htmlFor="type">Tipo</Label>
              <Select value={type} onValueChange={setType}>
                <SelectTrigger className="mt-1" data-testid="type-select">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Todos</SelectItem>
                  <SelectItem value="parcelas">Parcelas</SelectItem>
                  <SelectItem value="alvara">Alvará Judicial</SelectItem>
                  <SelectItem value="entrada">Entrada</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </div>

        {data && (
          <>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
              <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-6">
                <div className="flex items-center space-x-3 mb-2">
                  <DollarSign className="w-5 h-5 text-emerald-600" />
                  <h3 className="text-sm font-semibold text-slate-600">Total Recebido</h3>
                </div>
                <p className="text-2xl font-bold text-emerald-600 font-mono">
                  {formatCurrency(data.kpis.total_received)}
                </p>
              </div>

              <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-6">
                <div className="flex items-center space-x-3 mb-2">
                  <TrendingUp className="w-5 h-5 text-blue-600" />
                  <h3 className="text-sm font-semibold text-slate-600">Beneficiário 31</h3>
                </div>
                <p className="text-2xl font-bold text-slate-900 font-mono">
                  {formatCurrency(data.kpis.total_31)}
                </p>
              </div>

              <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-6">
                <div className="flex items-center space-x-3 mb-2">
                  <TrendingUp className="w-5 h-5 text-purple-600" />
                  <h3 className="text-sm font-semibold text-slate-600">Beneficiário 14</h3>
                </div>
                <p className="text-2xl font-bold text-slate-900 font-mono">
                  {formatCurrency(data.kpis.total_14)}
                </p>
              </div>

              <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-6">
                <div className="flex items-center space-x-3 mb-2">
                  <FileText className="w-5 h-5 text-slate-600" />
                  <h3 className="text-sm font-semibold text-slate-600">Casos com Recebimentos</h3>
                </div>
                <p className="text-2xl font-bold text-slate-900">
                  {data.kpis.cases_with_receipts}
                </p>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
              <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-6">
                <h3 className="font-semibold text-slate-900 mb-2">Parcelas</h3>
                <p className="text-2xl font-bold text-blue-600 font-mono">
                  {formatCurrency(data.kpis.total_parcelas)}
                </p>
              </div>

              <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-6">
                <h3 className="font-semibold text-slate-900 mb-2">Alvarás</h3>
                <p className="text-2xl font-bold text-purple-600 font-mono">
                  {formatCurrency(data.kpis.total_alvaras)}
                </p>
              </div>
            </div>

            <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-6 mb-8">
              <div className="flex justify-between items-center mb-6">
                <h3 className="text-lg font-semibold text-slate-900">Consolidado Mensal</h3>
              </div>
              {chartData.length > 0 ? (
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="month" />
                    <YAxis />
                    <Tooltip formatter={(value) => formatCurrency(value)} />
                    <Legend />
                    <Bar dataKey="31" fill="#3b82f6" name="Benef. 31" />
                    <Bar dataKey="14" fill="#a855f7" name="Benef. 14" />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <p className="text-center text-slate-500 py-8">Nenhum dado para exibir</p>
              )}
            </div>

            <div className="bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden">
              <div className="p-6 border-b border-slate-200 flex justify-between items-center">
                <h3 className="text-lg font-semibold text-slate-900">Recebimentos Detalhados</h3>
                <Button
                  onClick={exportToCSV}
                  variant="outline"
                  size="sm"
                  data-testid="export-csv-button"
                >
                  <Download className="w-4 h-4 mr-2" />
                  Exportar CSV
                </Button>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full" data-testid="receipts-table">
                  <thead className="bg-slate-50 border-b border-slate-200">
                    <tr>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                        Data
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                        Devedor
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                        Nº Processo
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                        Tipo
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                        Valor
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                        Beneficiário
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                        Observações
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200">
                    {data.receipts.map((receipt, index) => (
                      <tr
                        key={index}
                        className="table-row cursor-pointer hover:bg-slate-50"
                        onClick={() => navigate(`/cases/${receipt.case_id}`)}
                        data-testid={`receipt-row-${index}`}
                      >
                        <td className="px-6 py-4 font-mono text-slate-900">{formatDateBR(receipt.date)}</td>
                        <td className="px-6 py-4 font-medium text-slate-900">{receipt.debtor}</td>
                        <td className="px-6 py-4 font-mono text-slate-600 text-sm">
                          {receipt.numero_processo || '-'}
                        </td>
                        <td className="px-6 py-4">
                          <Badge variant="outline">{receipt.type}</Badge>
                        </td>
                        <td className="px-6 py-4 font-mono text-emerald-600 font-semibold">
                          {formatCurrency(receipt.value)}
                        </td>
                        <td className="px-6 py-4">
                          {receipt.beneficiario ? (
                            <Badge className="bg-slate-900 text-white">{receipt.beneficiario}</Badge>
                          ) : (
                            <span className="text-slate-400">-</span>
                          )}
                        </td>
                        <td className="px-6 py-4 text-slate-700 text-sm">{receipt.observacoes || '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {data.receipts.length === 0 && (
                <div className="text-center py-12" data-testid="no-receipts">
                  <p className="text-slate-500">Nenhum recebimento encontrado no período selecionado</p>
                </div>
              )}
            </div>

            {data.monthly_consolidation && data.monthly_consolidation.length > 0 && (
              <div className="bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden mt-8">
                <div className="p-6 border-b border-slate-200">
                  <h3 className="text-lg font-semibold text-slate-900">Consolidado Mensal Detalhado</h3>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full" data-testid="monthly-consolidation-table">
                    <thead className="bg-slate-50 border-b border-slate-200">
                      <tr>
                        <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                          Mês
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                          Benef. 31
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                          Benef. 14
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                          Parcelas
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                          Alvarás
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                          Total
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200">
                      {data.monthly_consolidation.map((month) => (
                        <tr key={month.month} className="table-row">
                          <td className="px-6 py-4 font-mono font-medium text-slate-900">{month.month}</td>
                          <td className="px-6 py-4 font-mono text-slate-900">{formatCurrency(month.total_31)}</td>
                          <td className="px-6 py-4 font-mono text-slate-900">{formatCurrency(month.total_14)}</td>
                          <td className="px-6 py-4 font-mono text-blue-600">{formatCurrency(month.total_parcelas)}</td>
                          <td className="px-6 py-4 font-mono text-purple-600">{formatCurrency(month.total_alvaras)}</td>
                          <td className="px-6 py-4 font-mono font-bold text-emerald-600">{formatCurrency(month.total)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
