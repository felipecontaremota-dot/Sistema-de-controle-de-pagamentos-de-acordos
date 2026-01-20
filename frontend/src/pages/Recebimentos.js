
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

const BACKEND_URL = (process.env.REACT_APP_API_URL || "").replace(/\/$/, "");
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
    ].join('\\n');

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

  const exportToPDF = async () => {
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

      const response = await axios.get(`${API}/receipts/pdf?${params.toString()}`, {
        headers: { Authorization: `Bearer ${token}` },
        responseType: 'blob',
      });

      const blob = new Blob([response.data], { type: 'application/pdf' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `recebimentos_${new Date().toISOString().split('T')[0]}.pdf`);
      document.body.appendChild(link);
      link.click();
      link.remove();

      toast.success('PDF gerado com sucesso!');
    } catch (error) {
      toast.error('Erro ao gerar PDF');
    }
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

        {data and content truncated for brevity...}
