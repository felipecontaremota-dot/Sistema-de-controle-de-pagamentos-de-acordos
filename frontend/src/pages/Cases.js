import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '../components/ui/dialog';
import { Label } from '../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { toast } from 'sonner';
import { Plus, Search, LogOut, Scale, Filter } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export default function Cases({ token, setToken }) {
  const [cases, setCases] = useState([]);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [beneficiaryFilter, setBeneficiaryFilter] = useState('');
  const [loading, setLoading] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [formData, setFormData] = useState({
    debtor_name: '',
    internal_id: '',
    value_causa: '',
    polo_ativo_text: '',
    notes: '',
  });
  const navigate = useNavigate();

  const fetchCases = async () => {
    try {
      const params = new URLSearchParams();
      if (search) params.append('search', search);
      if (statusFilter && statusFilter !== 'all') params.append('status_acordo', statusFilter);
      if (beneficiaryFilter && beneficiaryFilter !== 'all') params.append('beneficiario', beneficiaryFilter);

      const response = await axios.get(`${API}/cases?${params.toString()}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setCases(response.data);
    } catch (error) {
      if (error.response?.status === 401) {
        setToken(null);
        navigate('/login');
      } else {
        toast.error('Erro ao carregar casos');
      }
    }
  };

  useEffect(() => {
    fetchCases();
  }, [search, statusFilter, beneficiaryFilter]);

  const handleCreateCase = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      await axios.post(
        `${API}/cases`,
        {
          ...formData,
          value_causa: parseFloat(formData.value_causa),
        },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      toast.success('Caso criado com sucesso!');
      setDialogOpen(false);
      setFormData({
        debtor_name: '',
        internal_id: '',
        value_causa: '',
        polo_ativo_text: '',
        notes: '',
      });
      fetchCases();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao criar caso');
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    setToken(null);
    navigate('/login');
  };

  const getStatusBadge = (status) => {
    const statusConfig = {
      Quitado: { bg: 'bg-emerald-100', text: 'text-emerald-800', border: 'border-emerald-200' },
      'Em andamento': { bg: 'bg-blue-100', text: 'text-blue-800', border: 'border-blue-200' },
      'Em atraso': { bg: 'bg-rose-100', text: 'text-rose-800', border: 'border-rose-200' },
      Descumprido: { bg: 'bg-slate-100', text: 'text-slate-600', border: 'border-slate-200' },
      'Dia de pagamento': { bg: 'bg-amber-100', text: 'text-amber-800', border: 'border-amber-200' },
    };

    const config = statusConfig[status] || statusConfig['Em andamento'];
    return (
      <Badge
        className={`${config.bg} ${config.text} border ${config.border} status-badge`}
        data-testid={`status-badge-${status}`}
      >
        {status || 'Sem acordo'}
      </Badge>
    );
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <nav className="bg-white border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center space-x-3">
              <Scale className="w-8 h-8 text-slate-900" />
              <h1 className="text-xl font-bold text-slate-900">Acordos Judiciais</h1>
            </div>
            <Button
              onClick={handleLogout}
              variant="ghost"
              className="hover:bg-slate-100"
              data-testid="logout-button"
            >
              <LogOut className="w-5 h-5 mr-2" />
              Sair
            </Button>
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-8">
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-6">
            <div>
              <h2 className="text-3xl font-bold text-slate-900">Casos</h2>
              <p className="text-sm text-slate-600 mt-1">Gerencie seus casos e acordos judiciais</p>
            </div>
            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
              <DialogTrigger asChild>
                <Button className="bg-slate-900 hover:bg-slate-800" data-testid="create-case-button">
                  <Plus className="w-5 h-5 mr-2" />
                  Novo Caso
                </Button>
              </DialogTrigger>
              <DialogContent data-testid="create-case-dialog">
                <DialogHeader>
                  <DialogTitle>Criar Novo Caso</DialogTitle>
                </DialogHeader>
                <form onSubmit={handleCreateCase} className="space-y-4">
                  <div>
                    <Label htmlFor="debtor_name">Nome do devedor *</Label>
                    <Input
                      id="debtor_name"
                      value={formData.debtor_name}
                      onChange={(e) => setFormData({ ...formData, debtor_name: e.target.value })}
                      required
                      data-testid="debtor-name-input"
                    />
                  </div>
                  <div>
                    <Label htmlFor="internal_id">ID interno</Label>
                    <Input
                      id="internal_id"
                      value={formData.internal_id}
                      onChange={(e) => setFormData({ ...formData, internal_id: e.target.value })}
                      data-testid="internal-id-input"
                    />
                  </div>
                  <div>
                    <Label htmlFor="value_causa">Valor da causa *</Label>
                    <Input
                      id="value_causa"
                      type="number"
                      step="0.01"
                      value={formData.value_causa}
                      onChange={(e) => setFormData({ ...formData, value_causa: e.target.value })}
                      required
                      data-testid="value-causa-input"
                    />
                  </div>
                  <div>
                    <Label htmlFor="polo_ativo_text">Polo ativo (beneficiário) *</Label>
                    <Input
                      id="polo_ativo_text"
                      value={formData.polo_ativo_text}
                      onChange={(e) => setFormData({ ...formData, polo_ativo_text: e.target.value })}
                      placeholder="Ex: Banco 31 - Conta principal"
                      required
                      data-testid="polo-ativo-input"
                    />
                  </div>
                  <div>
                    <Label htmlFor="notes">Observações</Label>
                    <Input
                      id="notes"
                      value={formData.notes}
                      onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                      data-testid="notes-input"
                    />
                  </div>
                  <Button type="submit" className="w-full" disabled={loading} data-testid="submit-case-button">
                    {loading ? 'Criando...' : 'Criar Caso'}
                  </Button>
                </form>
              </DialogContent>
            </Dialog>
          </div>

          <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-4 space-y-4">
            <div className="flex items-center space-x-2">
              <Filter className="w-5 h-5 text-slate-600" />
              <h3 className="font-semibold text-slate-900">Filtros</h3>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <Label htmlFor="search">Buscar por devedor</Label>
                <div className="relative mt-1">
                  <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-slate-400" />
                  <Input
                    id="search"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Nome do devedor..."
                    className="pl-10"
                    data-testid="search-input"
                  />
                </div>
              </div>
              <div>
                <Label htmlFor="status-filter">Status do acordo</Label>
                <Select value={statusFilter || undefined} onValueChange={setStatusFilter}>
                  <SelectTrigger className="mt-1" data-testid="status-filter">
                    <SelectValue placeholder="Todos" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todos</SelectItem>
                    <SelectItem value="Quitado">Quitado</SelectItem>
                    <SelectItem value="Em andamento">Em andamento</SelectItem>
                    <SelectItem value="Em atraso">Em atraso</SelectItem>
                    <SelectItem value="Descumprido">Descumprido</SelectItem>
                    <SelectItem value="Dia de pagamento">Dia de pagamento</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label htmlFor="beneficiary-filter">Beneficiário</Label>
                <Select value={beneficiaryFilter || undefined} onValueChange={setBeneficiaryFilter}>
                  <SelectTrigger className="mt-1" data-testid="beneficiary-filter">
                    <SelectValue placeholder="Todos" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todos</SelectItem>
                    <SelectItem value="31">31</SelectItem>
                    <SelectItem value="14">14</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full" data-testid="cases-table">
              <thead className="bg-slate-50 border-b border-slate-200">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                    Devedor
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                    Valor da Causa
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                    Beneficiário
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                    Total Recebido
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                    % Recuperado
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                    Status
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200">
                {cases.map((case_) => (
                  <tr
                    key={case_.id}
                    onClick={() => navigate(`/cases/${case_.id}`)}
                    className="table-row cursor-pointer"
                    data-testid={`case-row-${case_.id}`}
                  >
                    <td className="px-6 py-4">
                      <div>
                        <div className="font-medium text-slate-900">{case_.debtor_name}</div>
                        {case_.internal_id && (
                          <div className="text-xs text-slate-500 font-mono">ID: {case_.internal_id}</div>
                        )}
                      </div>
                    </td>
                    <td className="px-6 py-4 font-mono text-slate-900">
                      R$ {case_.value_causa.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                    </td>
                    <td className="px-6 py-4">
                      {case_.polo_ativo_codigo ? (
                        <Badge className="bg-slate-900 text-white">{case_.polo_ativo_codigo}</Badge>
                      ) : (
                        <span className="text-slate-400">-</span>
                      )}
                    </td>
                    <td className="px-6 py-4 font-mono text-slate-900">
                      R$ {case_.total_received.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center space-x-2">
                        <div className="flex-1 bg-slate-200 rounded-full h-2 max-w-[80px]">
                          <div
                            className="bg-emerald-600 h-2 rounded-full"
                            style={{ width: `${Math.min(case_.percent_recovered, 100)}%` }}
                          />
                        </div>
                        <span className="text-sm font-medium text-slate-700">{case_.percent_recovered}%</span>
                      </div>
                    </td>
                    <td className="px-6 py-4">{getStatusBadge(case_.status_acordo)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {cases.length === 0 && (
            <div className="text-center py-12" data-testid="empty-state">
              <p className="text-slate-500">Nenhum caso encontrado</p>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
