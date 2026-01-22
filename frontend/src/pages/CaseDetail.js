import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import axios from 'axios';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '../components/ui/dialog';
import { Label } from '../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '../components/ui/alert-dialog';
import { toast } from 'sonner';
import { ArrowLeft, Plus, Scale, FileText, Calendar, DollarSign, Pencil, Trash2, AlertCircle } from 'lucide-react';
import { formatDateBR, formatCurrency } from '../utils/formatters';

/**
 * IMPORTANTE:
 * - Em produção (Render), variáveis REACT_APP_* só entram no build se estiverem definidas no ambiente de build.
 * - Seu projeto já usa REACT_APP_API_URL em outras telas (ex.: Login).
 * - Aqui padronizamos a origem da URL para evitar "/undefined/api/..." no frontend.
 */
const BACKEND_URL = (process.env.REACT_APP_API_URL || process.env.REACT_APP_BACKEND_URL || 'https://legacord-backend.onrender.com')
  .replace(/\/$/, '');

const API = `${BACKEND_URL}/api`;

export default function CaseDetail({ token, setToken }) {
  const { id } = useParams();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [agreementDialogOpen, setAgreementDialogOpen] = useState(false);
  const [paymentDialogOpen, setPaymentDialogOpen] = useState(false);
  const [alvaraDialogOpen, setAlvaraDialogOpen] = useState(false);
  const [editAlvaraDialogOpen, setEditAlvaraDialogOpen] = useState(false);
  const [deleteAlvaraDialogOpen, setDeleteAlvaraDialogOpen] = useState(false);
  const [deleteCaseDialogOpen, setDeleteCaseDialogOpen] = useState(false);
  const [deleteAgreementDialogOpen, setDeleteAgreementDialogOpen] = useState(false);
  const [selectedInstallment, setSelectedInstallment] = useState(null);
  const [selectedAlvara, setSelectedAlvara] = useState(null);
  const [alvaraToDelete, setAlvaraToDelete] = useState(null);
  const [editAgreementDialogOpen, setEditAgreementDialogOpen] = useState(false);

  const [agreementForm, setAgreementForm] = useState({
    total_value: '',
    installments_count: '',
    installment_value: '',
    first_due_date: '',
    has_entry: false,
    entry_value: '',
    entry_via_alvara: false,
    entry_date: '',
  });

  const [paymentForm, setPaymentForm] = useState({
    paid_date: '',
    paid_value: '',
    due_date: '',
  });

  const [alvaraForm, setAlvaraForm] = useState({
    data_alvara: '',
    valor_alvara: '',
    beneficiario_codigo: '31',
    observacoes: '',
  });

  const navigate = useNavigate();

  const handleUnauthorized = useCallback(() => {
    setToken(null);
    navigate('/login');
  }, [navigate, setToken]);

  const fetchCaseDetail = useCallback(async () => {
    // Se não houver token, não faz request (evita chamadas quebradas e loop de erro)
    if (!token) {
      handleUnauthorized();
      return;
    }

    try {
      const response = await axios.get(`${API}/cases/${id}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setData(response.data);
    } catch (error) {
      if (error.response?.status === 401) {
        handleUnauthorized();
      } else if (error.response?.status === 404) {
        toast.error('Caso não encontrado (404).');
      } else {
        toast.error('Erro ao carregar detalhes do caso');
      }
    }
  }, [id, token, handleUnauthorized]);

  useEffect(() => {
    fetchCaseDetail();
  }, [fetchCaseDetail]);

  // Cálculo automático do valor da parcela
  useEffect(() => {
    const { total_value, installments_count, has_entry, entry_value } = agreementForm;

    if (
      total_value &&
      installments_count &&
      parseFloat(total_value) > 0 &&
      parseInt(installments_count, 10) > 0
    ) {
      const totalValue = parseFloat(total_value);
      const entryVal = has_entry && entry_value ? parseFloat(entry_value) : 0;
      const baseValue = totalValue - entryVal;
      const installmentVal = baseValue / parseInt(installments_count, 10);

      setAgreementForm((prev) => ({
        ...prev,
        installment_value: installmentVal.toFixed(2),
      }));
    }
  }, [
    agreementForm.total_value,
    agreementForm.installments_count,
    agreementForm.has_entry,
    agreementForm.entry_value,
  ]);

  // Calcular data da primeira parcela automaticamente quando há entrada (1 mês calendário)
  useEffect(() => {
    if (agreementForm.has_entry && agreementForm.entry_date) {
      const entryDate = new Date(agreementForm.entry_date + 'T00:00:00');
      // Adicionar 1 mês calendário
      const firstDueDate = new Date(entryDate);
      firstDueDate.setMonth(firstDueDate.getMonth() + 1);

      // Ajustar para último dia do mês se dia não existir
      if (firstDueDate.getDate() !== entryDate.getDate()) {
        firstDueDate.setDate(0); // Último dia do mês anterior
      }

      const formattedDate = firstDueDate.toISOString().split('T')[0];

      setAgreementForm((prev) => ({
        ...prev,
        first_due_date: formattedDate,
      }));
    }
  }, [agreementForm.has_entry, agreementForm.entry_date]);

  const handleCreateAgreement = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      await axios.post(
        `${API}/agreements`,
        {
          case_id: id,
          total_value: parseFloat(agreementForm.total_value),
          installments_count: parseInt(agreementForm.installments_count, 10),
          installment_value: parseFloat(agreementForm.installment_value),
          first_due_date: agreementForm.first_due_date,
          has_entry: agreementForm.has_entry,
          entry_value: agreementForm.has_entry ? parseFloat(agreementForm.entry_value) : null,
          entry_via_alvara: agreementForm.entry_via_alvara,
          entry_date: agreementForm.has_entry ? agreementForm.entry_date : null,
        },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      toast.success('Acordo criado com sucesso!');
      setAgreementDialogOpen(false);
      fetchCaseDetail();
    } catch (error) {
      if (error.response?.status === 401) {
        handleUnauthorized();
      } else {
        toast.error(error.response?.data?.detail || 'Erro ao criar acordo');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleMarkAsPaid = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      await axios.put(
        `${API}/installments/${selectedInstallment.id}`,
        {
          paid_date: paymentForm.paid_date,
          paid_value: paymentForm.paid_value === '' ? null : parseFloat(paymentForm.paid_value),
          due_date: paymentForm.due_date,
        },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      toast.success('Parcela atualizada com sucesso!');
      setPaymentDialogOpen(false);
      setPaymentForm({ paid_date: '', paid_value: '', due_date: '' });
      setSelectedInstallment(null);
      fetchCaseDetail();
    } catch (error) {
      if (error.response?.status === 401) {
        handleUnauthorized();
      } else {
        toast.error(error.response?.data?.detail || 'Erro ao atualizar parcela');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleCreateAlvara = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      await axios.post(
        `${API}/alvaras`,
        {
          case_id: id,
          ...alvaraForm,
          valor_alvara: parseFloat(alvaraForm.valor_alvara),
        },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      toast.success('Alvará cadastrado com sucesso!');
      setAlvaraDialogOpen(false);
      setAlvaraForm({
        data_alvara: '',
        valor_alvara: '',
        beneficiario_codigo: '31',
        observacoes: '',
      });
      fetchCaseDetail();
    } catch (error) {
      if (error.response?.status === 401) {
        handleUnauthorized();
      } else {
        toast.error(error.response?.data?.detail || 'Erro ao cadastrar alvará');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateAlvara = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      await axios.put(
        `${API}/alvaras/${selectedAlvara.id}`,
        {
          ...alvaraForm,
          valor_alvara: parseFloat(alvaraForm.valor_alvara),
        },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      toast.success('Alvará atualizado com sucesso!');
      setEditAlvaraDialogOpen(false);
      setSelectedAlvara(null);
      fetchCaseDetail();
    } catch (error) {
      if (error.response?.status === 401) {
        handleUnauthorized();
      } else {
        toast.error(error.response?.data?.detail || 'Erro ao atualizar alvará');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteAlvara = async () => {
    setLoading(true);

    try {
      await axios.delete(`${API}/alvaras/${alvaraToDelete.id}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      toast.success('Alvará excluído com sucesso!');
      setDeleteAlvaraDialogOpen(false);
      setAlvaraToDelete(null);
      fetchCaseDetail();
    } catch (error) {
      if (error.response?.status === 401) {
        handleUnauthorized();
      } else {
        toast.error('Erro ao excluir alvará');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteCase = async () => {
    setLoading(true);

    try {
      await axios.delete(`${API}/cases/${id}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      toast.success('Caso excluído com sucesso!');
      navigate('/cases');
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

  const handleDeleteAgreement = async () => {
    setLoading(true);

    try {
      // proteção extra
      if (!data?.agreement?.id) {
        toast.error('Não há acordo para excluir.');
        setDeleteAgreementDialogOpen(false);
        return;
      }

      await axios.delete(`${API}/agreements/${data.agreement.id}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      toast.success('Acordo excluído com sucesso!');
      setDeleteAgreementDialogOpen(false);
      fetchCaseDetail();
    } catch (error) {
      if (error.response?.status === 401) {
        handleUnauthorized();
      } else {
        toast.error('Erro ao excluir acordo');
      }
    } finally {
      setLoading(false);
    }
  };

const handleUpdateAgreement = async (e) => {
  e.preventDefault();
  setLoading(true);

  try {
    await axios.put(
      `${API}/agreements/${data.agreement.id}`,
      {
        total_value: parseFloat(agreementForm.total_value),
        installments_count: parseInt(agreementForm.installments_count, 10),
        installment_value: parseFloat(agreementForm.installment_value),
        first_due_date: agreementForm.first_due_date,
        has_entry: agreementForm.has_entry,
        entry_value: agreementForm.has_entry
          ? parseFloat(agreementForm.entry_value)
          : null,
        entry_via_alvara: agreementForm.entry_via_alvara,
        entry_date: agreementForm.has_entry
          ? agreementForm.entry_date
          : null,
      },
      {
        headers: { Authorization: `Bearer ${token}` },
      }
    );

    toast.success("Acordo atualizado com sucesso!");
    setEditAgreementDialogOpen(false);
    fetchCaseDetail();
  } catch (error) {
    if (error.response?.status === 401) {
      handleUnauthorized();
    } else {
      toast.error(
        error.response?.data?.detail || "Erro ao atualizar acordo"
      );
    }
  } finally {
    setLoading(false);
  }
};
  

  const handleToggleAlvaraStatus = async (alvara) => {
    const newStatus = alvara.status_alvara === 'Aguardando alvará' ? 'Alvará pago' : 'Aguardando alvará';

    try {
      await axios.put(
        `${API}/alvaras/${alvara.id}`,
        { status_alvara: newStatus },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      toast.success(`Status alterado para: ${newStatus}`);
      fetchCaseDetail();
    } catch (error) {
      if (error.response?.status === 401) {
        handleUnauthorized();
      } else {
        toast.error('Erro ao atualizar status do alvará');
      }
    }
  };

  const getStatusBadge = (status) => {
    const statusConfig = {
      Pago: { bg: 'bg-emerald-100', text: 'text-emerald-800', border: 'border-emerald-200' },
      'Pagamento próximo': { bg: 'bg-amber-100', text: 'text-amber-800', border: 'border-amber-200' },
      'Dia de pagamento': { bg: 'bg-amber-100', text: 'text-amber-800', border: 'border-amber-200' },
      Atrasado: { bg: 'bg-rose-100', text: 'text-rose-800', border: 'border-rose-200' },
      Descumprido: { bg: 'bg-black', text: 'text-white', border: 'border-black' },
      Pendente: { bg: 'bg-blue-100', text: 'text-blue-800', border: 'border-blue-200' },
    };

    const config = statusConfig[status] || statusConfig['Pendente'];
    return (
      <Badge className={`${config.bg} ${config.text} border ${config.border} status-badge`}>
        {status}
      </Badge>
    );
  };

  if (!data) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <p className="text-slate-600">Carregando...</p>
      </div>
    );
  }

  const totalAlvaras = (data.alvaras || []).reduce((sum, alv) => sum + (alv?.valor_alvara || 0), 0);

  return (
    <div className="min-h-screen bg-slate-50">
      <nav className="bg-white border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center space-x-3">
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
                <Scale className="w-8 h-8 text-slate-900" />
                <div>
                  <h1 className="text-xl font-bold text-slate-900">{data.case.debtor_name}</h1>
                  {data.case.numero_processo && (
                    <p className="text-xs text-slate-500 font-mono">Processo: {data.case.numero_processo}</p>
                  )}
                </div>
              </div>
            </div>
            <Button
              onClick={() => setDeleteCaseDialogOpen(true)}
              variant="outline"
              className="text-rose-600 hover:bg-rose-50 border-rose-200"
              data-testid="delete-case-button"
            >
              <Trash2 className="w-4 h-4 mr-2" />
              Excluir Caso
            </Button>
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
          <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-6" data-testid="value-causa-card">
            <div className="flex items-center space-x-3 mb-2">
              <FileText className="w-5 h-5 text-blue-600" />
              <h3 className="text-sm font-semibold text-slate-600">Valor da Causa</h3>
            </div>
            <p className="text-2xl font-bold text-slate-900 font-mono">
              {formatCurrency(data.case.value_causa)}
            </p>
          </div>

          <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-6" data-testid="total-received-card">
            <div className="flex items-center space-x-3 mb-2">
              <DollarSign className="w-5 h-5 text-emerald-600" />
              <h3 className="text-sm font-semibold text-slate-600">Total Recebido</h3>
            </div>
            <p className="text-2xl font-bold text-emerald-600 font-mono">
              {formatCurrency(data.total_received)}
            </p>
          </div>

          <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-6" data-testid="percent-recovered-card">
            <div className="flex items-center space-x-3 mb-2">
              <Calendar className="w-5 h-5 text-slate-600" />
              <h3 className="text-sm font-semibold text-slate-600">% Recuperado</h3>
            </div>
            <div className="flex items-center space-x-3">
              <div className="flex-1 bg-slate-200 rounded-full h-3">
                <div
                  className="bg-emerald-600 h-3 rounded-full"
                  style={{ width: `${Math.min(data.percent_recovered, 100)}%` }}
                />
              </div>
              <span className="text-2xl font-bold text-slate-900">{data.percent_recovered}%</span>
            </div>
          </div>
        </div>

        <Tabs defaultValue="acordo" className="space-y-6">
          <TabsList className="bg-white border border-slate-200" data-testid="tabs-list">
            <TabsTrigger value="acordo" data-testid="tab-acordo">Acordo</TabsTrigger>
            <TabsTrigger value="parcelas" data-testid="tab-parcelas">Parcelas</TabsTrigger>
            <TabsTrigger value="alvara" data-testid="tab-alvara">Alvará Judicial</TabsTrigger>
            <TabsTrigger value="resumo" data-testid="tab-resumo">Resumo</TabsTrigger>
          </TabsList>

          <TabsContent value="acordo" data-testid="acordo-tab-content">
            <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-6">
              {data.agreement ? (
                <div className="space-y-4">
                  <div className="flex justify-between items-center">
                    <h3 className="text-lg font-semibold text-slate-900">Detalhes do Acordo</h3>

                    <div className="flex flex-col gap-2">
                     <Button
                       onClick={() => setDeleteAgreementDialogOpen(true)}
                       variant="outline"
                       size="sm"
                       className="text-rose-600 hover:bg-rose-50 border-rose-200"
                       data-testid="delete-agreement-button"
                     >
                       <Trash2 className="w-4 h-4 mr-2" />
                       Excluir Acordo
                     </Button>

                     <Button
                        onClick={() => {
                          setAgreementForm({
                            total_value: data.agreement.total_value,
                            installments_count: data.agreement.installments_count,
                            installment_value: data.agreement.installment_value,
                            first_due_date: data.agreement.first_due_date,
                            has_entry: data.agreement.has_entry,
                            entry_value: data.agreement.entry_value || '',
                            entry_via_alvara: data.agreement.entry_via_alvara,
                            entry_date: data.agreement.entry_date || '',
                          });
                        setEditAgreementDialogOpen(true);
                    }}
                    variant="outline"
                    size="sm"
                    className="border-slate-300 text-slate-700 hover:bg-slate-100"
                    data-testid="edit-agreement-button"
                  >
 
                      <Pencil className="w-4 h-4 mr-2" />
                       Editar Acordo
                     </Button>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <p className="text-sm text-slate-600">Valor total</p>
                      <p className="text-lg font-semibold text-slate-900 font-mono">
                        {formatCurrency(data.agreement.total_value)}
                      </p>
                    </div>
                    <div>
                      <p className="text-sm text-slate-600">Número de parcelas</p>
                      <p className="text-lg font-semibold text-slate-900">{data.agreement.installments_count}</p>
                    </div>
                    <div>
                      <p className="text-sm text-slate-600">Valor da parcela</p>
                      <p className="text-lg font-semibold text-slate-900 font-mono">
                        {formatCurrency(data.agreement.installment_value)}
                      </p>
                    </div>
                    <div>
                      <p className="text-sm text-slate-600">Data da 1ª parcela</p>
                      <p className="text-lg font-semibold text-slate-900">{formatDateBR(data.agreement.first_due_date)}</p>
                    </div>
                    {data.agreement.has_entry && (
                      <>
                        <div>
                          <p className="text-sm text-slate-600">Entrada</p>
                          <p className="text-lg font-semibold text-emerald-600 font-mono">
                            {formatCurrency(data.agreement.entry_value)}
                          </p>
                        </div>
                        <div>
                          <p className="text-sm text-slate-600">Data da entrada</p>
                          <p className="text-lg font-semibold text-slate-900">{formatDateBR(data.agreement.entry_date)}</p>
                        </div>
                        {data.agreement.entry_via_alvara && (
                          <div className="col-span-2">
                            <Badge className="bg-blue-100 text-blue-800 border-blue-200">
                              Entrada via Alvará Judicial
                            </Badge>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                </div>
                    
    <Dialog
      open={agreementDialogOpen}
      onOpenChange={setAgreementDialogOpen}
    >
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Editar Acordo</DialogTitle>
          <DialogDescription>
            Atualize os dados do acordo
          </DialogDescription>
        </DialogHeader>

        <form
          onSubmit={handleUpdateAgreement}
          className="space-y-4"
        >
          {/* reutilize os mesmos Inputs do Criar Acordo */}
          <Button
            type="submit"
            className="w-full"
            disabled={loading}
          >
            {loading ? 'Salvando...' : 'Salvar Alterações'}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  </>
) : (
  {/* bloco “Nenhum acordo cadastrado” */}
)}

              ) : (
                <div className="text-center py-8">
                  <p className="text-slate-600 mb-4">Nenhum acordo cadastrado para este caso</p>
                  <Dialog open={agreementDialogOpen} onOpenChange={setAgreementDialogOpen}>
                    <DialogTrigger asChild>
                      <Button className="bg-slate-900 hover:bg-slate-800" data-testid="create-agreement-button">
                        <Plus className="w-5 h-5 mr-2" />
                        Criar Acordo
                      </Button>
                    </DialogTrigger>
                    <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="create-agreement-dialog">
                      <DialogHeader>
                        <DialogTitle>Criar Acordo</DialogTitle>
                        <DialogDescription>Configure o acordo judicial com parcelas mensais</DialogDescription>
                      </DialogHeader>
                      <form onSubmit={handleCreateAgreement} className="space-y-4">
                        <div className="grid grid-cols-2 gap-4">
                          <div>
                            <Label htmlFor="total_value">Valor total do acordo *</Label>
                            <Input
                              id="total_value"
                              type="number"
                              step="0.01"
                              value={agreementForm.total_value}
                              onChange={(e) => setAgreementForm({ ...agreementForm, total_value: e.target.value })}
                              required
                              data-testid="total-value-input"
                            />
                          </div>
                          <div>
                            <Label htmlFor="installments_count">Número de parcelas *</Label>
                            <Input
                              id="installments_count"
                              type="number"
                              value={agreementForm.installments_count}
                              onChange={(e) =>
                                setAgreementForm({ ...agreementForm, installments_count: e.target.value })
                              }
                              required
                              data-testid="installments-count-input"
                            />
                          </div>
                        </div>

                        <div className="border-t pt-4">
                          <div className="flex items-center space-x-2 mb-3">
                            <Label htmlFor="has_entry">Há pagamento de entrada?</Label>
                            <Select
                              value={agreementForm.has_entry ? 'sim' : 'nao'}
                              onValueChange={(value) => setAgreementForm({ ...agreementForm, has_entry: value === 'sim' })}
                            >
                              <SelectTrigger className="w-32" data-testid="has-entry-select">
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="nao">Não</SelectItem>
                                <SelectItem value="sim">Sim</SelectItem>
                              </SelectContent>
                            </Select>
                          </div>

                          {agreementForm.has_entry && (
                            <div className="space-y-4 bg-slate-50 p-4 rounded-lg">
                              <div className="grid grid-cols-2 gap-4">
                                <div>
                                  <Label htmlFor="entry_value">Valor da entrada *</Label>
                                  <Input
                                    id="entry_value"
                                    type="number"
                                    step="0.01"
                                    value={agreementForm.entry_value}
                                    onChange={(e) => setAgreementForm({ ...agreementForm, entry_value: e.target.value })}
                                    required={agreementForm.has_entry}
                                    data-testid="entry-value-input"
                                  />
                                </div>
                                <div>
                                  <Label htmlFor="entry_date">
                                    Data da entrada {agreementForm.entry_via_alvara ? '(opcional)' : '*'}
                                  </Label>
                                  <Input
                                    id="entry_date"
                                    type="date"
                                    value={agreementForm.entry_date}
                                    onChange={(e) => setAgreementForm({ ...agreementForm, entry_date: e.target.value })}
                                    required={agreementForm.has_entry && !agreementForm.entry_via_alvara}
                                    data-testid="entry-date-input"
                                  />
                                  {agreementForm.entry_via_alvara && (
                                    <p className="text-xs text-slate-500 mt-1">
                                      Aguardando liberação judicial
                                    </p>
                                  )}
                                </div>
                              </div>
                              <div className="flex items-center space-x-2">
                                <input
                                  type="checkbox"
                                  id="entry_via_alvara"
                                  checked={agreementForm.entry_via_alvara}
                                  onChange={(e) => setAgreementForm({ ...agreementForm, entry_via_alvara: e.target.checked })}
                                  className="rounded"
                                  data-testid="entry-via-alvara-checkbox"
                                />
                                <Label htmlFor="entry_via_alvara" className="cursor-pointer">
                                  Entrada via Alvará Judicial
                                </Label>
                              </div>
                            </div>
                          )}
                        </div>

                        <div className="grid grid-cols-2 gap-4">
                          <div>
                            <Label htmlFor="installment_value">Valor da parcela (calculado)</Label>
                            <Input
                              id="installment_value"
                              type="number"
                              step="0.01"
                              value={agreementForm.installment_value}
                              onChange={(e) =>
                                setAgreementForm({ ...agreementForm, installment_value: e.target.value })
                              }
                              required
                              className="bg-slate-50"
                              data-testid="installment-value-input"
                            />
                            <p className="text-xs text-amber-600 mt-1 flex items-center">
                              <AlertCircle className="w-3 h-3 mr-1" />
                              Valor calculado automaticamente
                            </p>
                          </div>
                          <div>
                            <Label htmlFor="first_due_date">Data da 1ª parcela *</Label>
                            <Input
                              id="first_due_date"
                              type="date"
                              value={agreementForm.first_due_date}
                              onChange={(e) => setAgreementForm({ ...agreementForm, first_due_date: e.target.value })}
                              required
                              data-testid="first-due-date-input"
                            />
                            {agreementForm.has_entry && agreementForm.entry_date && (
                              <p className="text-xs text-blue-600 mt-1">
                                Gerada automaticamente (entrada + 1 mês)
                              </p>
                            )}
                          </div>
                        </div>

                        <Button type="submit" className="w-full" disabled={loading} data-testid="submit-agreement-button">
                          {loading ? 'Criando...' : 'Criar Acordo'}
                        </Button>
                      </form>
                    </DialogContent>
                  </Dialog>
                </div>
              )}
            </div>
          </TabsContent>

          <TabsContent value="parcelas" data-testid="parcelas-tab-content">
            <div className="bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden">
              {data.installments && data.installments.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full" data-testid="installments-table">
                    <thead className="bg-slate-50 border-b border-slate-200">
                      <tr>
                        <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                          Parcela
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                          Vencimento
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                          Data Pagamento
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                          Valor Pago
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                          Status
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                          Ações
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200">
                      {data.installments.map((inst) => (
                        <tr key={inst.id} className="table-row" data-testid={`installment-row-${inst.id}`}>
                          <td className="px-6 py-4 font-medium text-slate-900">
                            {inst.is_entry ? 'Entrada' : `#${inst.number}`}
                          </td>
                          <td className="px-6 py-4 font-mono text-slate-900">{formatDateBR(inst.due_date)}</td>
                          <td className="px-6 py-4 font-mono text-slate-900">
                            {inst.paid_date ? formatDateBR(inst.paid_date) : <span className="text-slate-400">-</span>}
                          </td>
                          <td className="px-6 py-4 font-mono text-slate-900">
                            {inst.paid_value ? formatCurrency(inst.paid_value) : <span className="text-slate-400">-</span>}
                          </td>
                          <td className="px-6 py-4">{getStatusBadge(inst.status_calc)}</td>
                          <td className="px-6 py-4">
                            <Dialog
                              open={paymentDialogOpen && selectedInstallment?.id === inst.id}
                              onOpenChange={(open) => {
                                setPaymentDialogOpen(open);
                                if (!open) setSelectedInstallment(null);
                              }}
                            >
                              <DialogTrigger asChild>
                                <Button
                                  size="sm"
                                  variant="outline"
                                  onClick={() => {
                                    setSelectedInstallment(inst);
                                    setPaymentForm({
                                      paid_date: inst.paid_date || '',
                                      paid_value: inst.paid_value || data.agreement?.installment_value || '',
                                      due_date: inst.due_date,
                                    });
                                  }}
                                  data-testid={`edit-installment-${inst.id}`}
                                >
                                  <Pencil className="w-4 h-4 mr-1" />
                                  Editar
                                </Button>
                              </DialogTrigger>
                              <DialogContent data-testid="payment-dialog">
                                <DialogHeader>
                                  <DialogTitle>Editar Parcela #{inst.number}</DialogTitle>
                                  <DialogDescription>Informe a data e o valor do pagamento recebido</DialogDescription>
                                </DialogHeader>
                                <form onSubmit={handleMarkAsPaid} className="space-y-4">
                                  <div>
                                    <Label htmlFor="due_date">Data de vencimento</Label>
                                    <Input
                                      id="due_date"
                                      type="date"
                                      value={paymentForm.due_date}
                                      onChange={(e) => setPaymentForm({ ...paymentForm, due_date: e.target.value })}
                                      disabled={inst.status_calc === 'Pago'}
                                      data-testid="due-date-input"
                                    />
                                  </div>
                                  <div>
                                    <Label htmlFor="paid_date">Data do pagamento</Label>
                                    <Input
                                      id="paid_date"
                                      type="date"
                                      value={paymentForm.paid_date}
                                      onChange={(e) => setPaymentForm({ ...paymentForm, paid_date: e.target.value })}
                                      data-testid="paid-date-input"
                                    />
                                  </div>
                                  <div>
                                    <Label htmlFor="paid_value">Valor pago</Label>
                                    <Input
                                      id="paid_value"
                                      type="number"
                                      step="0.01"
                                      value={paymentForm.paid_value}
                                      onChange={(e) => setPaymentForm({ ...paymentForm, paid_value: e.target.value })}
                                      data-testid="paid-value-input"
                                    />
                                  </div>
                                  <Button type="submit" className="w-full" disabled={loading} data-testid="submit-payment-button">
                                    {loading ? 'Salvando...' : 'Salvar'}
                                  </Button>
                                </form>
                              </DialogContent>
                            </Dialog>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="text-center py-12" data-testid="no-installments">
                  <p className="text-slate-500">Nenhuma parcela encontrada. Crie um acordo primeiro.</p>
                </div>
              )}
            </div>
          </TabsContent>

          <TabsContent value="alvara" data-testid="alvara-tab-content">
            <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-6">
              <div className="flex justify-between items-center mb-6">
                <div>
                  <h3 className="text-lg font-semibold text-slate-900">Alvarás Judiciais</h3>
                  <p className="text-sm text-slate-600 mt-1">
                    Total de alvarás: <span className="font-mono font-semibold text-emerald-600">{formatCurrency(totalAlvaras)}</span>
                  </p>
                </div>
                <Dialog open={alvaraDialogOpen} onOpenChange={setAlvaraDialogOpen}>
                  <DialogTrigger asChild>
                    <Button className="bg-slate-900 hover:bg-slate-800" data-testid="create-alvara-button">
                      <Plus className="w-5 h-5 mr-2" />
                      Novo Alvará
                    </Button>
                  </DialogTrigger>
                  <DialogContent data-testid="create-alvara-dialog">
                    <DialogHeader>
                      <DialogTitle>Cadastrar Alvará Judicial</DialogTitle>
                      <DialogDescription>Registre um novo alvará judicial recebido</DialogDescription>
                    </DialogHeader>
                    <form onSubmit={handleCreateAlvara} className="space-y-4">
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <Label htmlFor="data_alvara">Data do alvará *</Label>
                          <Input
                            id="data_alvara"
                            type="date"
                            value={alvaraForm.data_alvara}
                            onChange={(e) => setAlvaraForm({ ...alvaraForm, data_alvara: e.target.value })}
                            required
                            data-testid="data-alvara-input"
                          />
                        </div>
                        <div>
                          <Label htmlFor="valor_alvara">Valor do alvará *</Label>
                          <Input
                            id="valor_alvara"
                            type="number"
                            step="0.01"
                            value={alvaraForm.valor_alvara}
                            onChange={(e) => setAlvaraForm({ ...alvaraForm, valor_alvara: e.target.value })}
                            required
                            data-testid="valor-alvara-input"
                          />
                        </div>
                      </div>
                      <div>
                        <Label htmlFor="beneficiario_codigo">Beneficiário *</Label>
                        <Select
                          value={alvaraForm.beneficiario_codigo}
                          onValueChange={(value) => setAlvaraForm({ ...alvaraForm, beneficiario_codigo: value })}
                        >
                          <SelectTrigger data-testid="beneficiario-select">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="31">31</SelectItem>
                            <SelectItem value="14">14</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <div>
                        <Label htmlFor="observacoes">Observações</Label>
                        <Input
                          id="observacoes"
                          value={alvaraForm.observacoes}
                          onChange={(e) => setAlvaraForm({ ...alvaraForm, observacoes: e.target.value })}
                          data-testid="observacoes-input"
                        />
                      </div>
                      <Button type="submit" className="w-full" disabled={loading} data-testid="submit-alvara-button">
                        {loading ? 'Salvando...' : 'Cadastrar Alvará'}
                      </Button>
                    </form>
                  </DialogContent>
                </Dialog>
              </div>

              {data.alvaras && data.alvaras.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full" data-testid="alvaras-table">
                    <thead className="bg-slate-50 border-b border-slate-200">
                      <tr>
                        <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                          Data
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                          Valor
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                          Beneficiário
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                          Status
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                          Observações
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                          Ações
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200">
                      {data.alvaras.map((alvara) => (
                        <tr key={alvara.id} className="table-row" data-testid={`alvara-row-${alvara.id}`}>
                          <td className="px-6 py-4 font-mono text-slate-900">
                            {alvara.data_alvara ? formatDateBR(alvara.data_alvara) : '-'}
                          </td>
                          <td className="px-6 py-4 font-mono text-emerald-600 font-semibold">
                            {formatCurrency(alvara.valor_alvara)}
                          </td>
                          <td className="px-6 py-4">
                            <Badge className="bg-slate-900 text-white">{alvara.beneficiario_codigo}</Badge>
                          </td>
                          <td className="px-6 py-4">
                            <Badge
                              className={
                                alvara.status_alvara === 'Alvará pago'
                                  ? 'bg-emerald-100 text-emerald-800 border-emerald-200'
                                  : 'bg-amber-100 text-amber-800 border-amber-200'
                              }
                            >
                              {alvara.status_alvara}
                            </Badge>
                          </td>
                          <td className="px-6 py-4 text-slate-700">{alvara.observacoes || '-'}</td>
                          <td className="px-6 py-4">
                            <div className="flex space-x-2">
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => handleToggleAlvaraStatus(alvara)}
                                className={
                                  alvara.status_alvara === 'Aguardando alvará'
                                    ? 'text-emerald-600 hover:bg-emerald-50'
                                    : 'text-amber-600 hover:bg-amber-50'
                                }
                                data-testid={`toggle-alvara-status-${alvara.id}`}
                              >
                                {alvara.status_alvara === 'Aguardando alvará' ? 'Marcar como Pago' : 'Marcar como Aguardando'}
                              </Button>
                              <Dialog
                                open={editAlvaraDialogOpen && selectedAlvara?.id === alvara.id}
                                onOpenChange={(open) => {
                                  setEditAlvaraDialogOpen(open);
                                  if (!open) setSelectedAlvara(null);
                                }}
                              >
                                <DialogTrigger asChild>
                                  <Button
                                    size="sm"
                                    variant="outline"
                                    onClick={() => {
                                      setSelectedAlvara(alvara);
                                      setAlvaraForm({
                                        data_alvara: alvara.data_alvara,
                                        valor_alvara: alvara.valor_alvara,
                                        beneficiario_codigo: alvara.beneficiario_codigo,
                                        observacoes: alvara.observacoes || '',
                                      });
                                    }}
                                    data-testid={`edit-alvara-${alvara.id}`}
                                  >
                                    <Pencil className="w-4 h-4" />
                                  </Button>
                                </DialogTrigger>
                                <DialogContent>
                                  <DialogHeader>
                                    <DialogTitle>Editar Alvará</DialogTitle>
                                    <DialogDescription>Atualize os dados do alvará judicial</DialogDescription>
                                  </DialogHeader>
                                  <form onSubmit={handleUpdateAlvara} className="space-y-4">
                                    <div className="grid grid-cols-2 gap-4">
                                      <div>
                                        <Label htmlFor="edit_data_alvara">Data do alvará *</Label>
                                        <Input
                                          id="edit_data_alvara"
                                          type="date"
                                          value={alvaraForm.data_alvara}
                                          onChange={(e) => setAlvaraForm({ ...alvaraForm, data_alvara: e.target.value })}
                                          required
                                        />
                                      </div>
                                      <div>
                                        <Label htmlFor="edit_valor_alvara">Valor do alvará *</Label>
                                        <Input
                                          id="edit_valor_alvara"
                                          type="number"
                                          step="0.01"
                                          value={alvaraForm.valor_alvara}
                                          onChange={(e) => setAlvaraForm({ ...alvaraForm, valor_alvara: e.target.value })}
                                          required
                                        />
                                      </div>
                                    </div>
                                    <div>
                                      <Label htmlFor="edit_beneficiario_codigo">Beneficiário *</Label>
                                      <Select
                                        value={alvaraForm.beneficiario_codigo}
                                        onValueChange={(value) => setAlvaraForm({ ...alvaraForm, beneficiario_codigo: value })}
                                      >
                                        <SelectTrigger>
                                          <SelectValue />
                                        </SelectTrigger>
                                        <SelectContent>
                                          <SelectItem value="31">31</SelectItem>
                                          <SelectItem value="14">14</SelectItem>
                                        </SelectContent>
                                      </Select>
                                    </div>
                                    <div>
                                      <Label htmlFor="edit_observacoes">Observações</Label>
                                      <Input
                                        id="edit_observacoes"
                                        value={alvaraForm.observacoes}
                                        onChange={(e) => setAlvaraForm({ ...alvaraForm, observacoes: e.target.value })}
                                      />
                                    </div>
                                    <Button type="submit" className="w-full" disabled={loading}>
                                      {loading ? 'Salvando...' : 'Atualizar'}
                                    </Button>
                                  </form>
                                </DialogContent>
                              </Dialog>
                              <Button
                                size="sm"
                                variant="outline"
                                className="text-rose-600 hover:bg-rose-50"
                                onClick={() => {
                                  setAlvaraToDelete(alvara);
                                  setDeleteAlvaraDialogOpen(true);
                                }}
                                data-testid={`delete-alvara-${alvara.id}`}
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
              ) : (
                <div className="text-center py-12" data-testid="no-alvaras">
                  <p className="text-slate-500">Nenhum alvará cadastrado ainda.</p>
                </div>
              )}
            </div>
          </TabsContent>

          <TabsContent value="resumo" data-testid="resumo-tab-content">
            <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-6 space-y-6">
              <h3 className="text-lg font-semibold text-slate-900">Resumo do Caso</h3>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <h4 className="text-sm font-semibold text-slate-600 mb-3">Informações Básicas</h4>
                  <dl className="space-y-2">
                    <div>
                      <dt className="text-sm text-slate-600">Devedor</dt>
                      <dd className="text-base font-medium text-slate-900">{data.case.debtor_name}</dd>
                    </div>
                    {data.case.cpf && (
                      <div>
                        <dt className="text-sm text-slate-600">CPF</dt>
                        <dd className="text-base font-medium text-slate-900 font-mono">{data.case.cpf}</dd>
                      </div>
                    )}
                    {data.case.numero_processo && (
                      <div>
                        <dt className="text-sm text-slate-600">Número do Processo</dt>
                        <dd className="text-base font-medium text-slate-900 font-mono">{data.case.numero_processo}</dd>
                      </div>
                    )}
                    {data.case.status_processo && (
                      <div>
                        <dt className="text-sm text-slate-600">Status do Processo</dt>
                        <dd>
                          <Badge
                            variant="outline"
                            className={
                              data.case.status_processo === 'Extinto'
                                ? 'bg-black text-white border-black'
                                : data.case.status_processo === 'Acordo'
                                ? 'bg-amber-100 text-amber-800 border-amber-200'
                                : data.case.status_processo === 'Sucesso'
                                ? 'bg-emerald-100 text-emerald-800 border-emerald-200'
                                : ''
                            }
                          >
                            {data.case.status_processo}
                          </Badge>
                        </dd>
                      </div>
                    )}
                    {data.case.curso && (
                      <div>
                        <dt className="text-sm text-slate-600">Curso</dt>
                        <dd className="text-base text-slate-700">{data.case.curso}</dd>
                      </div>
                    )}
                    <div>
                      <dt className="text-sm text-slate-600">Polo Ativo</dt>
                      <dd className="text-base font-medium text-slate-900">{data.case.polo_ativo_text}</dd>
                    </div>
                  </dl>
                </div>

                <div>
                  <h4 className="text-sm font-semibold text-slate-600 mb-3">Valores</h4>
                  <dl className="space-y-2">
                    <div>
                      <dt className="text-sm text-slate-600">Valor da Causa</dt>
                      <dd className="text-base font-medium text-slate-900 font-mono">
                        {formatCurrency(data.case.value_causa)}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-sm text-slate-600">Total Recebido</dt>
                      <dd className="text-base font-medium text-emerald-600 font-mono">
                        {formatCurrency(data.total_received)}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-sm text-slate-600">Saldo Restante</dt>
                      <dd className="text-base font-medium text-slate-900 font-mono">
                        {formatCurrency(data.case.value_causa - data.total_received)}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-sm text-slate-600">% Recuperado</dt>
                      <dd className="text-base font-medium text-slate-900">{data.percent_recovered}%</dd>
                    </div>
                    {data.alvaras && data.alvaras.length > 0 && (
                      <div>
                        <dt className="text-sm text-slate-600">Total de Alvarás</dt>
                        <dd className="text-base font-medium text-emerald-600 font-mono">
                          {formatCurrency(totalAlvaras)}
                        </dd>
                      </div>
                    )}
                  </dl>
                </div>
              </div>

              {data.agreement && (
                <div>
                  <h4 className="text-sm font-semibold text-slate-600 mb-3">Status das Parcelas</h4>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="bg-emerald-50 rounded-lg p-4">
                      <p className="text-2xl font-bold text-emerald-700">
                        {data.installments.filter((i) => i.status_calc === 'Pago').length}
                      </p>
                      <p className="text-sm text-emerald-600">Pagas</p>
                    </div>
                    <div className="bg-blue-50 rounded-lg p-4">
                      <p className="text-2xl font-bold text-blue-700">
                        {data.installments.filter((i) => i.status_calc === 'Pendente').length}
                      </p>
                      <p className="text-sm text-blue-600">Pendentes</p>
                    </div>
                    <div className="bg-rose-50 rounded-lg p-4">
                      <p className="text-2xl font-bold text-rose-700">
                        {data.installments.filter((i) => i.status_calc === 'Atrasado').length}
                      </p>
                      <p className="text-sm text-rose-600">Atrasadas</p>
                    </div>
                    <div className="bg-slate-50 rounded-lg p-4">
                      <p className="text-2xl font-bold text-slate-700">
                        {data.installments.filter((i) => i.status_calc === 'Descumprido').length}
                      </p>
                      <p className="text-sm text-slate-600">Descumpridas</p>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </TabsContent>
        </Tabs>
      </main>

      <AlertDialog open={deleteAlvaraDialogOpen} onOpenChange={setDeleteAlvaraDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Confirmar exclusão</AlertDialogTitle>
            <AlertDialogDescription>
              Tem certeza que deseja excluir este alvará? Esta ação não pode ser desfeita.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={handleDeleteAlvara} className="bg-rose-600 hover:bg-rose-700">
              Excluir
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

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

      <AlertDialog open={deleteAgreementDialogOpen} onOpenChange={setDeleteAgreementDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Excluir Acordo</AlertDialogTitle>
            <AlertDialogDescription>
              Tem certeza que deseja excluir este acordo? Esta ação excluirá permanentemente o acordo e
              todas as parcelas vinculadas. O caso será mantido. Esta ação não pode ser desfeita.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={handleDeleteAgreement} className="bg-rose-600 hover:bg-rose-700">
              Excluir Acordo
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
