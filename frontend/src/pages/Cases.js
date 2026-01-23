import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from "../lib/api";

import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '../components/ui/dialog';
import { Label } from '../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '../components/ui/alert-dialog';
import { toast } from 'sonner';
import { Plus, Search, LogOut, Scale, Filter, DollarSign, Trash2, Upload } from 'lucide-react';
import { formatCurrency } from '../utils/formatters';

const STATUS_PROCESSO_OPTIONS = [
  'Execução',
  'Cobrança',
  'Cumprimento de Sentença',
  'Aguardando Alvará',
  'Acordo',
  'Sucesso',
  'Extinto'
];

const SORT_OPTIONS = [
  { value: 'recent', label: 'Mais recentes' },
  { value: 'debtor_name_asc', label: 'Ordem alfabética (devedor)' },
  { value: 'value_causa_asc', label: 'Menor valor da causa' },
  { value: 'value_causa_desc', label: 'Maior valor da causa' },
  { value: 'total_received_asc', label: 'Menor valor recebido' },
  { value: 'total_received_desc', label: 'Maior valor recebido' },
  { value: 'percent_recovered_asc', label: 'Menor % recuperado' },
  { value: 'percent_recovered_desc', label: 'Maior % recuperado' },
];

export default function Cases({ token, setToken }) {
  const [cases, setCases] = useState([]);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [beneficiaryFilter, setBeneficiaryFilter] = useState('');
  const [statusProcessoFilter, setStatusProcessoFilter] = useState('');
  const [sortOption, setSortOption] = useState('recent');
  const [loading, setLoading] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingCase, setEditingCase] = useState(null);
  const [deleteCaseDialogOpen, setDeleteCaseDialogOpen] = useState(false);
  const [caseToDelete, setCaseToDelete] = useState(null);

  const [formData, setFormData] = useState({
    debtor_name: '',
    internal_id: '',
    value_causa: '',
    polo_ativo_text: '',
    notes: '',
    numero_processo: '',
    data_protocolo: '',
    status_processo: '',
    data_matricula: '',
    cpf: '',
    curso: '',
  });

  const navigate = useNavigate();

  const handleUnauthorized = () => {
    setToken(null);
    navigate('/login');
  };

  const fetchCases = async () => {
    try {
      const params = new URLSearchParams();
      if (search) params.append('search', search);
      if (statusFilter && statusFilter !== 'all') params.append('status_acordo', statusFilter);
      if (beneficiaryFilter && beneficiaryFilter !== 'all') params.append('beneficiario', beneficiaryFilter);
      if (statusProcessoFilter && statusProcessoFilter !== 'all') params.append('status_processo', statusProcessoFilter);

      const response = await api.get(`/cases?${params.toString()}`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      setCases(response.data);
    } catch (error) {
      if (error.response?.status === 401) {
        handleUnauthorized();
      } else {
        toast.error('Erro ao carregar casos');
      }
    }
  };

  useEffect(() => {
    fetchCases();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, statusFilter, beneficiaryFilter, statusProcessoFilter]);

  const openCreateDialog = () => {
    setEditingCase(null);
    setFormData({
      debtor_name: '',
      internal_id: '',
      value_causa: '',
      polo_ativo_text: '',
      notes: '',
      numero_processo: '',
      data_protocolo: '',
      status_processo: '',
      data_matricula: '',
      cpf: '',
      curso: '',
    });
    setDialogOpen(true);
  };

  const openEditDialog = (caseData) => {
    setEditingCase(caseData);
    setFormData({
      debtor_name: caseData.debtor_name || '',
      internal_id: caseData.internal_id || '',
      value_causa: caseData.value_causa || '',
      polo_ativo_text: caseData.polo_ativo_text || '',
      notes: caseData.notes || '',
      numero_processo: caseData.numero_processo || '',
      data_protocolo: caseData.data_protocolo || '',
      status_processo: caseData.status_processo || '',
      data_matricula: caseData.data_matricula || '',
      cpf: caseData.cpf || '',
      curso: caseData.curso || '',
    });
    setDialogOpen(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      const payload = {
        ...formData,
        value_causa: parseFloat(formData.value_causa),
      };

      if (editingCase) {
        await api.put(`/cases/${editingCase.id}`, payload, {
          headers: { Authorization: `Bearer ${token}` },
        });
        toast.success('Caso atualizado com sucesso!');
      } else {
        await api.post(`/cases`, payload, {
          headers: { Authorization: `Bearer ${token}` },
        });
        toast.success('Caso criado com sucesso!');
      }

      setDialogOpen(false);
      fetchCases();
    } catch (error) {
      if (error.response?.status === 401) {
        handleUnauthorized();
      } else {
        toast.error(error.response?.data?.detail || 'Erro ao salvar caso');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteCase = async () => {
    setLoading(true);

    try {
      await api.delete(`/cases/${caseToDelete.id}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      toast.success('Caso excluído com sucesso!');
      setDeleteCaseDialogOpen(false);
      setCaseToDelete(null);
      fetchCases();
    } catch (error) {
      if (error.response?.status === 401) {
        handleUnauthorized();
      } else {
        toast.error('Erro ao excluir caso');
      }
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
  Descumprido: { bg: 'bg-black', text: 'text-white', border: 'border-black' },
  'Dia de pagamento': { bg: 'bg-amber-100', text: 'text-amber-800', border: 'border-amber-200' },

  // 👉 NOVO STATUS
  'Aguardando alvará': {
    bg: 'bg-purple-100',
    text: 'text-purple-800',
    border: 'border-purple-200',
  },
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

  const toNumericValue = (value) => {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  };

  const sortedCases = (() => {
    if (sortOption === 'recent') {
      return cases;
    }

    const casesCopy = [...cases];

    switch (sortOption) {
      case 'debtor_name_asc':
        return casesCopy.sort((a, b) =>
          (a.debtor_name || '').localeCompare(b.debtor_name || '', 'pt-BR', { sensitivity: 'base' })
        );
      case 'value_causa_asc':
        return casesCopy.sort((a, b) => toNumericValue(a.value_causa) - toNumericValue(b.value_causa));
      case 'value_causa_desc':
        return casesCopy.sort((a, b) => toNumericValue(b.value_causa) - toNumericValue(a.value_causa));
      case 'total_received_asc':
        return casesCopy.sort((a, b) => toNumericValue(a.total_received) - toNumericValue(b.total_received));
      case 'total_received_desc':
        return casesCopy.sort((a, b) => toNumericValue(b.total_received) - toNumericValue(a.total_received));
      case 'percent_recovered_asc':
        return casesCopy.sort((a, b) => toNumericValue(a.percent_recovered) - toNumericValue(b.percent_recovered));
      case 'percent_recovered_desc':
        return casesCopy.sort((a, b) => toNumericValue(b.percent_recovered) - toNumericValue(a.percent_recovered));
      default:
        return cases;
    }
  })();

  return (
    <div className="min-h-screen bg-slate-50">
      <nav className="bg-white border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center space-x-3">
              <Scale className="w-8 h-8 text-slate-900" />
              <h1 className="text-xl font-bold text-slate-900">Acordos Judiciais</h1>
            </div>
            <div className="flex items-center space-x-4">
              <Button
                onClick={() => navigate('/recebimentos')}
                variant="outline"
                className="hover:bg-slate-100"
                data-testid="recebimentos-button"
              >
                <DollarSign className="w-5 h-5 mr-2" />
                Recebimentos
              </Button>
              <Button
                onClick={() => navigate('/import')}
                variant="outline"
                className="hover:bg-slate-100"
                data-testid="import-button"
              >
                <Upload className="w-5 h-5 mr-2" />
                Importação
              </Button>
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
        </div>
      </nav>

      <main className="max-w-[1600px] mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-8">
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-6">
            <div>
              <h2 className="text-3xl font-bold text-slate-900">Casos</h2>
              <p className="text-sm text-slate-600 mt-1">Gerencie seus casos e acordos judiciais</p>
            </div>

            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
              <DialogTrigger asChild>
                <Button className="bg-slate-900 hover:bg-slate-800" onClick={openCreateDialog} data-testid="create-case-button">
                  <Plus className="w-5 h-5 mr-2" />
                  Novo Caso
                </Button>
              </DialogTrigger>

              <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="create-case-dialog">
                <DialogHeader>
                  <DialogTitle>{editingCase ? 'Editar Caso' : 'Criar Novo Caso'}</DialogTitle>
                  <DialogDescription>Preencha os dados do caso judicial</DialogDescription>
                </DialogHeader>

                <form onSubmit={handleSubmit} className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="col-span-2">
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
                      <Label htmlFor="cpf">CPF</Label>
                      <Input
                        id="cpf"
                        value={formData.cpf}
                        onChange={(e) => {
                          const value = e.target.value.replace(/\D/g, '');
                          const formatted = value
                            .replace(/(\d{3})(\d)/, '$1.$2')
                            .replace(/(\d{3})(\d)/, '$1.$2')
                            .replace(/(\d{3})(\d{1,2})/, '$1-$2')
                            .replace(/(-\d{2})\d+?$/, '$1');
                          setFormData({ ...formData, cpf: formatted });
                        }}
                        placeholder="000.000.000-00"
                        maxLength={14}
                        data-testid="cpf-input"
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
                  </div>

                  <div className="border-t pt-4">
                    <h3 className="font-semibold text-slate-900 mb-3">Dados do Processo</h3>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <Label htmlFor="numero_processo">Número do processo</Label>
                        <Input
                          id="numero_processo"
                          value={formData.numero_processo}
                          onChange={(e) => setFormData({ ...formData, numero_processo: e.target.value })}
                          data-testid="numero-processo-input"
                        />
                      </div>

                      <div>
                        <Label htmlFor="status_processo">Status do processo *</Label>
                        <Select
                          value={formData.status_processo}
                          onValueChange={(value) => setFormData({ ...formData, status_processo: value })}
                        >
                          <SelectTrigger data-testid="status-processo-select">
                            <SelectValue placeholder="Selecione o status" />
                          </SelectTrigger>
                          <SelectContent>
                            {STATUS_PROCESSO_OPTIONS.map((status) => (
                              <SelectItem key={status} value={status}>
                                {status}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>

                      <div>
                        <Label htmlFor="data_protocolo">Data do protocolo</Label>
                        <Input
                          id="data_protocolo"
                          type="date"
                          value={formData.data_protocolo}
                          onChange={(e) => setFormData({ ...formData, data_protocolo: e.target.value })}
                          data-testid="data-protocolo-input"
                        />
                      </div>

                      <div>
                        <Label htmlFor="data_matricula">Data da matrícula</Label>
                        <Input
                          id="data_matricula"
                          type="date"
                          value={formData.data_matricula}
                          onChange={(e) => setFormData({ ...formData, data_matricula: e.target.value })}
                          data-testid="data-matricula-input"
                        />
                      </div>

                      <div>
                        <Label htmlFor="curso">Curso</Label>
                        <Input
                          id="curso"
                          value={formData.curso}
                          onChange={(e) => setFormData({ ...formData, curso: e.target.value })}
                          data-testid="curso-input"
                        />
                      </div>
                    </div>
                  </div>

                  <div className="border-t pt-4">
                    <h3 className="font-semibold text-slate-900 mb-3">Dados Financeiros</h3>
                    <div className="grid grid-cols-2 gap-4">
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
                    </div>
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
                    {loading ? 'Salvando...' : editingCase ? 'Atualizar Caso' : 'Criar Caso'}
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

            <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
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

              <div>
                <Label htmlFor="status-processo-filter">Status do processo</Label>
                <Select value={statusProcessoFilter || undefined} onValueChange={setStatusProcessoFilter}>
                  <SelectTrigger className="mt-1" data-testid="status-processo-filter">
                    <SelectValue placeholder="Todos" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todos</SelectItem>
                    {STATUS_PROCESSO_OPTIONS.map((status) => (
                      <SelectItem key={status} value={status}>
                        {status}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div>
                <Label htmlFor="sort-cases">Ordenar por</Label>
                <Select value={sortOption} onValueChange={setSortOption}>
                  <SelectTrigger className="mt-1" data-testid="sort-cases">
                    <SelectValue placeholder="Mais recentes" />
                  </SelectTrigger>
                  <SelectContent>
                    {SORT_OPTIONS.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
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
                    Devedor / Processo
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                    Status Processo
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
                    Status Acordo
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                    Ações
                  </th>
                </tr>
              </thead>

              <tbody className="divide-y divide-slate-200">
                {sortedCases.map((case_) => (
                  <tr
                    key={case_.id}
                    className="table-row cursor-pointer"
                    onClick={() => navigate(`/cases/${case_.id}`)}
                    data-testid={`case-row-${case_.id}`}
                  >
                    <td className="px-6 py-4">
                      <div>
                        <div className="font-medium text-slate-900">{case_.debtor_name}</div>
                        {case_.numero_processo && (
                          <div className="text-xs text-slate-500 font-mono">Proc: {case_.numero_processo}</div>
                        )}
                        {case_.internal_id && (
                          <div className="text-xs text-slate-500 font-mono">ID: {case_.internal_id}</div>
                        )}
                      </div>
                    </td>

                    <td className="px-6 py-4">
                      {case_.status_processo ? (
                        <Badge
                          variant="outline"
                          className={
                            case_.status_processo === 'Extinto'
                              ? 'bg-black text-white border-black'
                              : case_.status_processo === 'Acordo'
                              ? 'bg-amber-100 text-amber-800 border-amber-200'
                              : case_.status_processo === 'Sucesso'
                              ? 'bg-emerald-100 text-emerald-800 border-emerald-200'
                              : 'text-xs'
                          }
                        >
                          {case_.status_processo}
                        </Badge>
                      ) : (
                        <span className="text-slate-400 text-xs">-</span>
                      )}
                    </td>

                    <td className="px-6 py-4 font-mono text-slate-900">
                      {formatCurrency(case_.value_causa)}
                    </td>

                    <td className="px-6 py-4">
                      {case_.polo_ativo_codigo ? (
                        <Badge className="bg-slate-900 text-white">{case_.polo_ativo_codigo}</Badge>
                      ) : (
                        <span className="text-slate-400">-</span>
                      )}
                    </td>

                    <td className="px-6 py-4 font-mono text-slate-900">
                      {formatCurrency(case_.total_received)}
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

                    <td className="px-6 py-4">
                      <div className="flex space-x-2">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={(e) => {
                            e.stopPropagation();
                            openEditDialog(case_);
                          }}
                          data-testid={`edit-case-${case_.id}`}
                        >
                          Editar
                        </Button>

                        <Button
                          size="sm"
                          variant="outline"
                          className="text-rose-600 hover:bg-rose-50"
                          onClick={(e) => {
                            e.stopPropagation();
                            setCaseToDelete(case_);
                            setDeleteCaseDialogOpen(true);
                          }}
                          data-testid={`delete-case-${case_.id}`}
                        >
                          <Trash2 className="w-4 h-4" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {sortedCases.length === 0 && (
            <div className="text-center py-12" data-testid="empty-state">
              <p className="text-slate-500">Nenhum caso encontrado</p>
            </div>
          )}
        </div>
      </main>

      <AlertDialog open={deleteCaseDialogOpen} onOpenChange={setDeleteCaseDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Excluir Caso</AlertDialogTitle>
            <AlertDialogDescription>
              Tem certeza que deseja excluir este caso? Esta ação excluirá permanentemente o caso, o acordo,
              todas as parcelas e alvarás vinculados. Esta ação não pode ser desfeita.
            </AlertDialogDescription>
          </AlertDialogHeader>

          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={handleDeleteCase} className="bg-rose-600 hover:bg-rose-700">
              Excluir Tudo
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
