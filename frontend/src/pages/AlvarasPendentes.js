import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Textarea } from '../components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { toast } from 'sonner';
import { ArrowLeft, FileText, CheckCircle2 } from 'lucide-react';
import { formatCurrency, formatDateBR } from '../utils/formatters';

const API_BASE =
  process.env.REACT_APP_API_URL ||
  process.env.REACT_APP_BACKEND_URL ||
  '';

const API = `${API_BASE}/api`;

export default function AlvarasPendentes({ token, setToken }) {
  const [alvaras, setAlvaras] = useState([]);
  const [loading, setLoading] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [selectedAlvara, setSelectedAlvara] = useState(null);
  const [formData, setFormData] = useState({
    data_alvara: '',
    valor_alvara: '',
    beneficiario_codigo: '',
    observacoes: '',
  });
  const [searchDebtor, setSearchDebtor] = useState('');
  const [searchProcess, setSearchProcess] = useState('');
  const [beneficiaryFilter, setBeneficiaryFilter] = useState('all');
  const [orderBy, setOrderBy] = useState('recent');
  const navigate = useNavigate();

  const handleUnauthorized = () => {
    setToken(null);
    navigate('/login');
  };

  const fetchAlvaras = async () => {
    setLoading(true);
    try {
      const response = await axios.get(`${API}/alvaras/pendentes`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setAlvaras(response.data);
    } catch (error) {
      if (error.response?.status === 401) {
        handleUnauthorized();
      } else {
        toast.error('Erro ao carregar alvarás pendentes');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAlvaras();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const openDialog = (alvara) => {
    setSelectedAlvara(alvara);
    setFormData({
      data_alvara: alvara.data || '',
      valor_alvara: alvara.valor ?? '',
      beneficiario_codigo: alvara.beneficiario || '',
      observacoes: alvara.observacoes || '',
    });
    setDialogOpen(true);
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!selectedAlvara) return;
    try {
      const payload = {
        data_alvara: formData.data_alvara,
        valor_alvara: Number(formData.valor_alvara),
        beneficiario_codigo: formData.beneficiario_codigo,
        observacoes: formData.observacoes,
        status_alvara: 'Alvará pago',
      };

      await axios.put(`${API}/alvaras/${selectedAlvara.alvara_id}`, payload, {
        headers: { Authorization: `Bearer ${token}` },
      });

      setAlvaras((prev) => prev.filter((item) => item.alvara_id !== selectedAlvara.alvara_id));
      setDialogOpen(false);
      setSelectedAlvara(null);
      toast.success('Alvará marcado como pago');
    } catch (error) {
      if (error.response?.status === 401) {
        handleUnauthorized();
      } else {
        toast.error('Erro ao atualizar alvará');
      }
    }
  };

    const filteredAlvaras = useMemo(() => {
    let result = [...alvaras];

    if (searchDebtor) {
      result = result.filter((alvara) =>
        alvara.devedor?.toLowerCase().includes(searchDebtor.toLowerCase())
      );
    }

    if (searchProcess) {
      result = result.filter((alvara) =>
        (alvara.numero_processo || '').includes(searchProcess)
      );
    }

    if (beneficiaryFilter !== 'all') {
      result = result.filter((alvara) => alvara.beneficiario === beneficiaryFilter);
    }

    switch (orderBy) {
      case 'alpha':
        result.sort((a, b) => (a.devedor || '').localeCompare(b.devedor || '', 'pt-BR'));
        break;
      case 'min':
        result.sort((a, b) => (a.valor || 0) - (b.valor || 0));
        break;
      case 'max':
        result.sort((a, b) => (b.valor || 0) - (a.valor || 0));
        break;
      default:
        result.sort((a, b) => new Date(b.data) - new Date(a.data));
    }

    return result;
  }, [alvaras, searchDebtor, searchProcess, beneficiaryFilter, orderBy]);
  
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
              <FileText className="w-8 h-8 text-emerald-600" />
              <h1 className="text-xl font-bold text-slate-900">Alvarás Pendentes</h1>
            </div>
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-6 mb-6">
          <h3 className="font-semibold text-slate-900 mb-4">Filtros</h3>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div>
              <Label htmlFor="search-debtor">Buscar por devedor</Label>
              <Input
                id="search-debtor"
                value={searchDebtor}
                onChange={(event) => setSearchDebtor(event.target.value)}
                placeholder="Digite o nome do devedor"
                className="mt-1"
                data-testid="search-debtor-input"
              />
            </div>
            <div>
              <Label htmlFor="search-process">Buscar por nº do processo</Label>
              <Input
                id="search-process"
                value={searchProcess}
                onChange={(event) => setSearchProcess(event.target.value)}
                placeholder="Digite o número do processo"
                className="mt-1"
                data-testid="search-process-input"
              />
            </div>
            <div>
              <Label htmlFor="beneficiary-filter">Beneficiário</Label>
              <Select value={beneficiaryFilter} onValueChange={setBeneficiaryFilter}>
                <SelectTrigger className="mt-1" data-testid="beneficiary-filter">
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
              <Label htmlFor="order-by">Ordenar por</Label>
              <Select value={orderBy} onValueChange={setOrderBy}>
                <SelectTrigger className="mt-1" data-testid="order-by">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="recent">Mais recentes</SelectItem>
                  <SelectItem value="alpha">Ordem alfabética (devedor)</SelectItem>
                  <SelectItem value="min">Menor valor</SelectItem>
                  <SelectItem value="max">Maior valor</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </div>                             
        <div className="bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden">
          <div className="p-6 border-b border-slate-200 flex justify-between items-center">
            <div>
              <h3 className="text-lg font-semibold text-slate-900">Pendências de Alvarás</h3>
              <p className="text-sm text-slate-600">Gerencie e dê baixa nos alvarás aguardando pagamento</p>
            </div>
            <div className="text-sm text-slate-600" data-testid="alvaras-count">
              {alvaras.length} pendente(s)
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full" data-testid="alvaras-pendentes-table">
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
                    Valor
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                    Beneficiário
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
                {filteredAlvaras.map((alvara) => (
                  <tr key={alvara.alvara_id} className="table-row hover:bg-slate-50">
                    <td className="px-6 py-4 font-mono text-slate-900">
                      {formatDateBR(alvara.data)}
                    </td>
                    <td className="px-6 py-4 font-medium text-slate-900">{alvara.devedor}</td>
                    <td className="px-6 py-4 font-mono text-slate-600 text-sm">
                      {alvara.numero_processo || '-'}
                    </td>
                    <td className="px-6 py-4 font-mono text-emerald-600 font-semibold">
                      {formatCurrency(alvara.valor)}
                    </td>
                    <td className="px-6 py-4 text-slate-700 text-sm">
                      {alvara.beneficiario || '-'}
                    </td>
                    <td className="px-6 py-4 text-slate-700 text-sm">
                      {alvara.observacoes || '-'}
                    </td>
                    <td className="px-6 py-4">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => openDialog(alvara)}
                        data-testid={`mark-paid-${alvara.alvara_id}`}
                      >
                        <CheckCircle2 className="w-4 h-4 mr-2" />
                        Marcar como pago
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {!loading && alvaras.length === 0 && (
            <div className="text-center py-12" data-testid="no-alvaras">
              <p className="text-slate-500">Nenhum alvará pendente encontrado</p>
            </div>
          )}
        </div>
      </main>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-lg" data-testid="alvara-modal">
          <DialogHeader>
            <DialogTitle>Baixa de Alvará</DialogTitle>
            <DialogDescription>Atualize os dados para marcar o alvará como pago.</DialogDescription>
          </DialogHeader>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <Label htmlFor="data_alvara">Data do alvará</Label>
              <Input
                id="data_alvara"
                type="date"
                value={formData.data_alvara}
                onChange={(e) => setFormData({ ...formData, data_alvara: e.target.value })}
                required
              />
            </div>
            <div>
              <Label htmlFor="valor_alvara">Valor do alvará</Label>
              <Input
                id="valor_alvara"
                type="number"
                step="0.01"
                value={formData.valor_alvara}
                onChange={(e) => setFormData({ ...formData, valor_alvara: e.target.value })}
                required
              />
            </div>
            <div>
              <Label htmlFor="beneficiario_codigo">Beneficiário</Label>
              <Input
                id="beneficiario_codigo"
                value={formData.beneficiario_codigo}
                onChange={(e) => setFormData({ ...formData, beneficiario_codigo: e.target.value })}
                placeholder="Informe o código do beneficiário"
              />
            </div>
            <div>
              <Label htmlFor="observacoes">Observações</Label>
              <Textarea
                id="observacoes"
                value={formData.observacoes}
                onChange={(e) => setFormData({ ...formData, observacoes: e.target.value })}
                rows={3}
                placeholder="Digite observações sobre o alvará"
              />
            </div>
            <div className="flex justify-end space-x-2">
              <Button type="button" variant="ghost" onClick={() => setDialogOpen(false)}>
                Cancelar
              </Button>
              <Button type="submit" className="bg-slate-900 hover:bg-slate-800">
                Confirmar baixa
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
