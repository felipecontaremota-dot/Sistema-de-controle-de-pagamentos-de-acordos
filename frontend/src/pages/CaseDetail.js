import { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import axios from 'axios';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '../components/ui/dialog';
import { Label } from '../components/ui/label';
import { toast } from 'sonner';
import { ArrowLeft, Plus, Scale, FileText, Calendar, DollarSign } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export default function CaseDetail({ token, setToken }) {
  const { id } = useParams();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [agreementDialogOpen, setAgreementDialogOpen] = useState(false);
  const [paymentDialogOpen, setPaymentDialogOpen] = useState(false);
  const [selectedInstallment, setSelectedInstallment] = useState(null);
  const [agreementForm, setAgreementForm] = useState({
    total_value: '',
    installments_count: '',
    installment_value: '',
    first_due_date: '',
  });
  const [paymentForm, setPaymentForm] = useState({
    paid_date: '',
    paid_value: '',
  });
  const navigate = useNavigate();

  const fetchCaseDetail = async () => {
    try {
      const response = await axios.get(`${API}/cases/${id}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setData(response.data);
    } catch (error) {
      if (error.response?.status === 401) {
        setToken(null);
        navigate('/login');
      } else {
        toast.error('Erro ao carregar detalhes do caso');
      }
    }
  };

  useEffect(() => {
    fetchCaseDetail();
  }, [id]);

  const handleCreateAgreement = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      await axios.post(
        `${API}/agreements`,
        {
          case_id: id,
          ...agreementForm,
          total_value: parseFloat(agreementForm.total_value),
          installments_count: parseInt(agreementForm.installments_count),
          installment_value: parseFloat(agreementForm.installment_value),
        },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      toast.success('Acordo criado com sucesso!');
      setAgreementDialogOpen(false);
      setAgreementForm({
        total_value: '',
        installments_count: '',
        installment_value: '',
        first_due_date: '',
      });
      fetchCaseDetail();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao criar acordo');
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
          paid_value: parseFloat(paymentForm.paid_value),
        },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      toast.success('Parcela atualizada com sucesso!');
      setPaymentDialogOpen(false);
      setPaymentForm({ paid_date: '', paid_value: '' });
      setSelectedInstallment(null);
      fetchCaseDetail();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao atualizar parcela');
    } finally {
      setLoading(false);
    }
  };

  const getStatusBadge = (status) => {
    const statusConfig = {
      Pago: { bg: 'bg-emerald-100', text: 'text-emerald-800', border: 'border-emerald-200' },
      'Pagamento próximo': { bg: 'bg-amber-100', text: 'text-amber-800', border: 'border-amber-200' },
      'Dia de pagamento': { bg: 'bg-amber-100', text: 'text-amber-800', border: 'border-amber-200' },
      Atrasado: { bg: 'bg-rose-100', text: 'text-rose-800', border: 'border-rose-200' },
      Descumprido: { bg: 'bg-slate-100', text: 'text-slate-600', border: 'border-slate-200' },
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
              <Scale className="w-8 h-8 text-slate-900" />
              <h1 className="text-xl font-bold text-slate-900">{data.case.debtor_name}</h1>
            </div>
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
              R$ {data.case.value_causa.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
            </p>
          </div>

          <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-6" data-testid="total-received-card">
            <div className="flex items-center space-x-3 mb-2">
              <DollarSign className="w-5 h-5 text-emerald-600" />
              <h3 className="text-sm font-semibold text-slate-600">Total Recebido</h3>
            </div>
            <p className="text-2xl font-bold text-emerald-600 font-mono">
              R$ {data.total_received.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
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
            <TabsTrigger value="resumo" data-testid="tab-resumo">Resumo</TabsTrigger>
          </TabsList>

          <TabsContent value="acordo" data-testid="acordo-tab-content">
            <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-6">
              {data.agreement ? (
                <div className="space-y-4">
                  <h3 className="text-lg font-semibold text-slate-900">Detalhes do Acordo</h3>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <p className="text-sm text-slate-600">Valor total</p>
                      <p className="text-lg font-semibold text-slate-900 font-mono">
                        R$ {data.agreement.total_value.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                      </p>
                    </div>
                    <div>
                      <p className="text-sm text-slate-600">Número de parcelas</p>
                      <p className="text-lg font-semibold text-slate-900">{data.agreement.installments_count}</p>
                    </div>
                    <div>
                      <p className="text-sm text-slate-600">Valor da parcela</p>
                      <p className="text-lg font-semibold text-slate-900 font-mono">
                        R$ {data.agreement.installment_value.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                      </p>
                    </div>
                    <div>
                      <p className="text-sm text-slate-600">Data da 1ª parcela</p>
                      <p className="text-lg font-semibold text-slate-900">{data.agreement.first_due_date}</p>
                    </div>
                  </div>
                </div>
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
                    <DialogContent data-testid="create-agreement-dialog">
                      <DialogHeader>
                        <DialogTitle>Criar Acordo</DialogTitle>
                      </DialogHeader>
                      <form onSubmit={handleCreateAgreement} className="space-y-4">
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
                        <div>
                          <Label htmlFor="installment_value">Valor da parcela *</Label>
                          <Input
                            id="installment_value"
                            type="number"
                            step="0.01"
                            value={agreementForm.installment_value}
                            onChange={(e) =>
                              setAgreementForm({ ...agreementForm, installment_value: e.target.value })
                            }
                            required
                            data-testid="installment-value-input"
                          />
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
                          <td className="px-6 py-4 font-medium text-slate-900">#{inst.number}</td>
                          <td className="px-6 py-4 font-mono text-slate-900">{inst.due_date}</td>
                          <td className="px-6 py-4 font-mono text-slate-900">
                            {inst.paid_date || <span className="text-slate-400">-</span>}
                          </td>
                          <td className="px-6 py-4 font-mono text-slate-900">
                            {inst.paid_value ? (
                              `R$ ${inst.paid_value.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`
                            ) : (
                              <span className="text-slate-400">-</span>
                            )}
                          </td>
                          <td className="px-6 py-4">{getStatusBadge(inst.status_calc)}</td>
                          <td className="px-6 py-4">
                            {inst.status_calc !== 'Pago' && (
                              <Dialog open={paymentDialogOpen && selectedInstallment?.id === inst.id} onOpenChange={(open) => {
                                setPaymentDialogOpen(open);
                                if (!open) setSelectedInstallment(null);
                              }}>
                                <DialogTrigger asChild>
                                  <Button
                                    size="sm"
                                    variant="outline"
                                    onClick={() => {
                                      setSelectedInstallment(inst);
                                      setPaymentForm({
                                        paid_date: '',
                                        paid_value: data.agreement?.installment_value || '',
                                      });
                                    }}
                                    data-testid={`mark-paid-button-${inst.id}`}
                                  >
                                    Marcar como pago
                                  </Button>
                                </DialogTrigger>
                                <DialogContent data-testid="payment-dialog">
                                  <DialogHeader>
                                    <DialogTitle>Registrar Pagamento - Parcela #{inst.number}</DialogTitle>
                                  </DialogHeader>
                                  <form onSubmit={handleMarkAsPaid} className="space-y-4">
                                    <div>
                                      <Label htmlFor="paid_date">Data do pagamento *</Label>
                                      <Input
                                        id="paid_date"
                                        type="date"
                                        value={paymentForm.paid_date}
                                        onChange={(e) => setPaymentForm({ ...paymentForm, paid_date: e.target.value })}
                                        required
                                        data-testid="paid-date-input"
                                      />
                                    </div>
                                    <div>
                                      <Label htmlFor="paid_value">Valor pago *</Label>
                                      <Input
                                        id="paid_value"
                                        type="number"
                                        step="0.01"
                                        value={paymentForm.paid_value}
                                        onChange={(e) => setPaymentForm({ ...paymentForm, paid_value: e.target.value })}
                                        required
                                        data-testid="paid-value-input"
                                      />
                                    </div>
                                    <Button type="submit" className="w-full" disabled={loading} data-testid="submit-payment-button">
                                      {loading ? 'Salvando...' : 'Salvar Pagamento'}
                                    </Button>
                                  </form>
                                </DialogContent>
                              </Dialog>
                            )}
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
                    {data.case.internal_id && (
                      <div>
                        <dt className="text-sm text-slate-600">ID Interno</dt>
                        <dd className="text-base font-medium text-slate-900 font-mono">{data.case.internal_id}</dd>
                      </div>
                    )}
                    <div>
                      <dt className="text-sm text-slate-600">Polo Ativo</dt>
                      <dd className="text-base font-medium text-slate-900">{data.case.polo_ativo_text}</dd>
                    </div>
                    {data.case.notes && (
                      <div>
                        <dt className="text-sm text-slate-600">Observações</dt>
                        <dd className="text-base text-slate-700">{data.case.notes}</dd>
                      </div>
                    )}
                  </dl>
                </div>

                <div>
                  <h4 className="text-sm font-semibold text-slate-600 mb-3">Valores</h4>
                  <dl className="space-y-2">
                    <div>
                      <dt className="text-sm text-slate-600">Valor da Causa</dt>
                      <dd className="text-base font-medium text-slate-900 font-mono">
                        R$ {data.case.value_causa.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-sm text-slate-600">Total Recebido</dt>
                      <dd className="text-base font-medium text-emerald-600 font-mono">
                        R$ {data.total_received.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-sm text-slate-600">Saldo Restante</dt>
                      <dd className="text-base font-medium text-slate-900 font-mono">
                        R$ {(data.case.value_causa - data.total_received).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-sm text-slate-600">% Recuperado</dt>
                      <dd className="text-base font-medium text-slate-900">{data.percent_recovered}%</dd>
                    </div>
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
    </div>
  );
}
