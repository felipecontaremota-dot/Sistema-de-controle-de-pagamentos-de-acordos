import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../lib/api';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Badge } from '../components/ui/badge';
import { Alert, AlertDescription, AlertTitle } from '../components/ui/alert';
import { Progress } from '../components/ui/progress';
import { toast } from 'sonner';
import {
  ArrowLeft,
  UploadCloud,
  FileSearch,
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
} from 'lucide-react';

const steps = [
  { id: 1, title: 'Upload', description: 'Envie o arquivo Excel/CSV' },
  { id: 2, title: 'Mapeamento', description: 'Mapeie colunas para campos do sistema' },
  { id: 3, title: 'Validação', description: 'Revise prévia, erros e avisos' },
  { id: 4, title: 'Confirmação', description: 'Confirme para gravar no banco' },
  { id: 5, title: 'Resultado', description: 'Resumo final e histórico' },
];

const MAX_FILE_SIZE_MB = 10;

const fieldSections = [
  {
    key: 'case',
    title: 'Caso Judicial',
    fields: [
      { key: 'debtor_name', label: 'Nome do devedor' },
      { key: 'internal_id', label: 'ID interno' },
      { key: 'value_causa', label: 'Valor da causa' },
      { key: 'polo_ativo_text', label: 'Polo ativo (texto)' },
      { key: 'notes', label: 'Observações' },
      { key: 'numero_processo', label: 'Número do processo' },
      { key: 'data_protocolo', label: 'Data de protocolo' },
      { key: 'status_processo', label: 'Status do processo' },
      { key: 'data_matricula', label: 'Data de matrícula' },
      { key: 'cpf', label: 'CPF' },
      { key: 'whatsapp', label: 'WhatsApp' },
      { key: 'email', label: 'E-mail' },      
      { key: 'curso', label: 'Curso' },
    ],
  },
  {
    key: 'agreement',
    title: 'Acordo',
    fields: [
      { key: 'total_value', label: 'Valor total' },
      { key: 'installments_count', label: 'Quantidade de parcelas' },
      { key: 'installment_value', label: 'Valor da parcela' },
      { key: 'first_due_date', label: 'Primeiro vencimento' },
      { key: 'has_entry', label: 'Possui entrada (sim/não)' },
      { key: 'entry_value', label: 'Valor da entrada' },
      { key: 'entry_via_alvara', label: 'Entrada via alvará (sim/não)' },
      { key: 'entry_date', label: 'Data da entrada' },
      { key: 'total_received_import', label: 'Total recebido' },      
    ],
  },
  {
    key: 'installment',
    title: 'Parcelas',
    fields: [
      { key: 'number', label: 'Número da parcela' },
      { key: 'due_date', label: 'Data de vencimento' },
      { key: 'paid_date', label: 'Data de pagamento' },
      { key: 'paid_value', label: 'Valor pago' },
      { key: 'is_entry', label: 'É entrada (sim/não)' },
    ],
  },
  {
    key: 'alvara',
    title: 'Alvarás Judiciais',
    fields: [
      { key: 'data_alvara', label: 'Data do alvará' },
      { key: 'valor_alvara', label: 'Valor do alvará' },
      { key: 'beneficiario_codigo', label: 'Beneficiário (31 ou 14)' },
      { key: 'observacoes', label: 'Observações' },
      { key: 'status_alvara', label: 'Status do alvará' },
    ],
  },
];

export default function Import({ setToken }) {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [file, setFile] = useState(null);
  const [sessionId, setSessionId] = useState('');
  const [columns, setColumns] = useState([]);
  const [preview, setPreview] = useState([]);
  const [totalRows, setTotalRows] = useState(0);
  const [loading, setLoading] = useState(false);
  const [validation, setValidation] = useState(null);
  const [history, setHistory] = useState([]);
  const [commitResult, setCommitResult] = useState(null);
  const [importResults, setImportResults] = useState([]);

  const initialMapping = useMemo(() => {
    return fieldSections.reduce((acc, section) => {
      acc[section.key] = section.fields.reduce((fieldAcc, field) => {
        fieldAcc[field.key] = '';
        return fieldAcc;
      }, {});
      return acc;
    }, {});
  }, []);

  const [mapping, setMapping] = useState(initialMapping);

  const resetWizard = () => {
    setStep(1);
    setFile(null);
    setSessionId('');
    setColumns([]);
    setPreview([]);
    setTotalRows(0);
    setMapping(initialMapping);
    setValidation(null);
    setCommitResult(null);
    setImportResults([]);
  };

  const fetchHistory = async () => {
    try {
      const response = await api.get('/import/history');
      setHistory(response.data || []);
    } catch (error) {
      if (error.response?.status === 401) {
        setToken(null);
        navigate('/login');
      }
    }
  };

  useEffect(() => {
    fetchHistory();
  }, []);

  const handleUpload = async () => {
    if (!file) {
      toast.error('Selecione um arquivo para continuar');
      return;
    }
    if (file.size > MAX_FILE_SIZE_MB * 1024 * 1024) {
      toast.error(`Arquivo excede ${MAX_FILE_SIZE_MB}MB`);
      return;
    }

    setLoading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const response = await api.post('/import/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setSessionId(response.data.session_id);
      await handlePreview(response.data.session_id);
      setStep(2);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao enviar arquivo');
    } finally {
      setLoading(false);
    }
  };

  const handlePreview = async (session) => {
    const response = await api.post('/import/preview', {
      session_id: session,
      sample_size: 10,
    });
    setColumns(response.data.columns || []);
    setPreview(response.data.preview || []);
    setTotalRows(response.data.total_rows || 0);
  };

  const handleMappingChange = (sectionKey, fieldKey, value) => {
    setMapping((prev) => ({
      ...prev,
      [sectionKey]: {
        ...prev[sectionKey],
        [fieldKey]: value === 'ignore' ? '' : value,
      },
    }));
  };

  const handleValidate = async () => {
    setLoading(true);
    try {
      const response = await api.post('/import/validate', {
        session_id: sessionId,
        mapping,
      });
      setValidation(response.data);
      setStep(3);
    } catch (error) {
      toast.error(error.response?.data?.detail?.message || 'Erro ao validar arquivo');
    } finally {
      setLoading(false);
    }
  };

  const handleCommit = async () => {
    setLoading(true);
    try {
      const response = await api.post('/import/commit', {
        session_id: sessionId,
        mapping,
      });
      toast.success(response.data.message || 'Importação concluída');
      setCommitResult(response.data);
      setImportResults(response.data.results || []);
      await fetchHistory();
      setStep(5);
    } catch (error) {
      const message = error.response?.data?.detail?.message || 'Erro ao confirmar importação';
      toast.error(message);
    } finally {
      setLoading(false);
    }
  };

  const renderStepper = () => (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        {steps.map((item, index) => {
          const isActive = step === item.id;
          const isComplete = step > item.id;
          return (
            <div key={item.id} className="flex-1 flex flex-col items-center text-center">
              <div
                className={`w-10 h-10 rounded-full flex items-center justify-center border-2 ${
                  isComplete
                    ? 'bg-emerald-500 border-emerald-500 text-white'
                    : isActive
                    ? 'bg-slate-900 border-slate-900 text-white'
                    : 'bg-white border-slate-200 text-slate-500'
                }`}
              >
                {item.id}
              </div>
              <span className="text-sm font-medium text-slate-900 mt-2">{item.title}</span>
              <span className="text-xs text-slate-500 hidden md:block">{item.description}</span>
              {index < steps.length - 1 && (
                <div className="hidden md:block w-full h-px bg-slate-200 mt-4" />
              )}
            </div>
          );
        })}
      </div>
      <Progress value={(step / steps.length) * 100} />
    </div>
  );

  return (
    <div className="min-h-screen bg-slate-50">
      <nav className="bg-white border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center space-x-3">
              <Button variant="ghost" onClick={() => navigate('/cases')}>
                <ArrowLeft className="w-5 h-5 mr-2" />
                Voltar
              </Button>
              <h1 className="text-xl font-bold text-slate-900">Importação de Dados</h1>
            </div>
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
        {renderStepper()}

        <Card>
          <CardHeader>
            <CardTitle>Wizard de Importação</CardTitle>
            <CardDescription>
              Nenhum dado é gravado no banco até a confirmação final do usuário.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {step === 1 && (
              <div className="space-y-4">
                <div className="flex items-center gap-3">
                  <UploadCloud className="w-6 h-6 text-slate-700" />
                  <div>
                    <h3 className="text-lg font-semibold text-slate-900">Envie o arquivo</h3>
                    <p className="text-sm text-slate-500">Formatos aceitos: .xlsx, .xls, .csv</p>
                  </div>
                </div>
                <Input
                  type="file"
                  accept=".xlsx,.xls,.csv"
                  onChange={(event) => setFile(event.target.files?.[0] || null)}
                />
                <p className="text-xs text-slate-500">Tamanho máximo: {MAX_FILE_SIZE_MB}MB</p>
                <div className="flex gap-3">
                  <Button onClick={handleUpload} disabled={loading} className="bg-slate-900 hover:bg-slate-800">
                    {loading ? 'Enviando...' : 'Enviar arquivo'}
                  </Button>
                </div>
              </div>
            )}

            {step === 2 && (
              <div className="space-y-6">
                <div className="flex items-center gap-3">
                  <FileSearch className="w-6 h-6 text-slate-700" />
                  <div>
                    <h3 className="text-lg font-semibold text-slate-900">Mapeamento das colunas</h3>
                    <p className="text-sm text-slate-500">Total de linhas detectadas: {totalRows}</p>
                  </div>
                </div>

                <div className="rounded-lg border border-slate-200 overflow-x-auto">
                  <table className="min-w-full text-sm">
                    <thead className="bg-slate-100">
                      <tr>
                        {columns.map((column) => (
                          <th key={column} className="px-4 py-2 text-left text-slate-600 font-medium">
                            {column}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {preview.map((row, index) => (
                        <tr key={`preview-${index}`} className="border-t border-slate-100">
                          {columns.map((column) => (
                            <td key={`${index}-${column}`} className="px-4 py-2 text-slate-700">
                              {row[column]}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <div className="space-y-6">
                  {fieldSections.map((section) => (
                    <div key={section.key} className="space-y-3">
                      <div className="flex items-center gap-2">
                        <h4 className="text-base font-semibold text-slate-900">{section.title}</h4>
                        <Badge variant="outline">{section.key}</Badge>
                      </div>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {section.fields.map((field) => (
                          <div key={field.key} className="space-y-2">
                            <label className="text-sm font-medium text-slate-700">
                              {field.label}
                            </label>
                            <Select
                              value={mapping[section.key][field.key] || ''}
                              onValueChange={(value) => handleMappingChange(section.key, field.key, value)}
                            >
                              <SelectTrigger>
                                <SelectValue placeholder="Selecione uma coluna" />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="ignore">Ignorar</SelectItem>
                                {columns.map((column) => (
                                  <SelectItem key={`${section.key}-${field.key}-${column}`} value={column}>
                                    {column}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>

                <div className="flex gap-3">
                  <Button variant="outline" onClick={() => setStep(1)}>
                    Voltar
                  </Button>
                  <Button onClick={handleValidate} disabled={loading} className="bg-slate-900 hover:bg-slate-800">
                    {loading ? 'Validando...' : 'Validar dados'}
                  </Button>
                </div>
              </div>
            )}

            {step === 3 && validation && (
              <div className="space-y-6">
                <div className="flex items-center gap-3">
                  <ShieldCheck className="w-6 h-6 text-slate-700" />
                  <div>
                    <h3 className="text-lg font-semibold text-slate-900">Validação concluída</h3>
                    <p className="text-sm text-slate-500">Revise os avisos e erros antes de confirmar.</p>
                  </div>
                </div>

                <div className="rounded-lg border border-slate-200 overflow-x-auto">
                  <table className="min-w-full text-sm">
                    <thead className="bg-slate-100">
                      <tr>
                        {columns.map((column) => (
                          <th key={`validation-${column}`} className="px-4 py-2 text-left text-slate-600 font-medium">
                            {column}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {preview.map((row, index) => (
                        <tr key={`validation-preview-${index}`} className="border-t border-slate-100">
                          {columns.map((column) => (
                            <td key={`validation-${index}-${column}`} className="px-4 py-2 text-slate-700">
                              {row[column]}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <Card>
                    <CardContent className="pt-6">
                      <p className="text-xs uppercase text-slate-500">Linhas totais</p>
                      <p className="text-2xl font-semibold text-slate-900">{validation.summary.total_rows}</p>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardContent className="pt-6">
                      <p className="text-xs uppercase text-slate-500">Linhas válidas</p>
                      <p className="text-2xl font-semibold text-emerald-600">{validation.summary.valid_rows}</p>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardContent className="pt-6">
                      <p className="text-xs uppercase text-slate-500">Linhas com erro</p>
                      <p className="text-2xl font-semibold text-rose-600">{validation.summary.invalid_rows}</p>
                    </CardContent>
                  </Card>
                </div>

                {validation.errors.length > 0 && (
                  <Alert variant="destructive">
                    <AlertTitle>Erros bloqueantes</AlertTitle>
                    <AlertDescription>
                      <ul className="list-disc pl-5 space-y-1">
                        {validation.errors.map((error, index) => (
                          <li key={`error-${index}`}>
                            {error.row ? `Linha ${error.row}: ` : ''}{error.message}
                          </li>
                        ))}
                      </ul>
                    </AlertDescription>
                  </Alert>
                )}

                {validation.warnings.length > 0 && (
                  <Alert>
                    <AlertTitle>Avisos</AlertTitle>
                    <AlertDescription>
                      <ul className="list-disc pl-5 space-y-1">
                        {validation.warnings.map((warning, index) => (
                          <li key={`warning-${index}`}>
                            {warning.row ? `Linha ${warning.row}: ` : ''}{warning.message}
                          </li>
                        ))}
                      </ul>
                    </AlertDescription>
                  </Alert>
                )}

                <div className="flex gap-3">
                  <Button variant="outline" onClick={() => setStep(2)}>
                    Voltar
                  </Button>
                  <Button
                    onClick={() => setStep(4)}
                    disabled={validation.errors.length > 0}
                    className="bg-slate-900 hover:bg-slate-800"
                  >
                    Prosseguir para confirmação
                  </Button>
                </div>
              </div>
            )}

            {step === 4 && (
              <div className="space-y-6">
                <div className="flex items-center gap-3">
                  <CheckCircle2 className="w-6 h-6 text-emerald-600" />
                  <div>
                    <h3 className="text-lg font-semibold text-slate-900">Confirmação final</h3>
                    <p className="text-sm text-slate-500">Revise e confirme para gravar os dados.</p>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <Card>
                    <CardContent className="pt-6">
                      <p className="text-xs uppercase text-slate-500">Linhas válidas</p>
                      <p className="text-2xl font-semibold text-emerald-600">{validation?.summary?.valid_rows || 0}</p>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardContent className="pt-6">
                      <p className="text-xs uppercase text-slate-500">Linhas com erro</p>
                      <p className="text-2xl font-semibold text-rose-600">{validation?.summary?.invalid_rows || 0}</p>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardContent className="pt-6">
                      <p className="text-xs uppercase text-slate-500">Total de linhas</p>
                      <p className="text-2xl font-semibold text-slate-900">{validation?.summary?.total_rows || 0}</p>
                    </CardContent>
                  </Card>
                </div>

                {validation?.errors?.length > 0 && (
                  <Alert variant="destructive">
                    <AlertTitle>Não é possível confirmar</AlertTitle>
                    <AlertDescription>
                      Existem erros bloqueantes. Corrija o arquivo antes de continuar.
                    </AlertDescription>
                  </Alert>
                )}

                {validation?.errors?.length === 0 && (
                  <Alert>
                    <AlertTitle>Confirmação obrigatória</AlertTitle>
                    <AlertDescription>
                      Ao confirmar, os dados serão gravados em definitivo. Esta ação é auditável.
                    </AlertDescription>
                  </Alert>
                )}

                <div className="flex gap-3">
                  <Button variant="outline" onClick={() => setStep(3)}>
                    Voltar
                  </Button>
                  <Button
                    onClick={handleCommit}
                    disabled={loading || validation?.errors?.length > 0}
                    className="bg-emerald-600 hover:bg-emerald-500"
                  >
                    {loading ? 'Gravando...' : 'Confirmar importação'}
                  </Button>
                </div>
              </div>
            )}

            {step === 5 && (
              <div className="space-y-6">
                <div className="flex items-center gap-3">
                  <CheckCircle2 className="w-6 h-6 text-emerald-600" />
                  <div>
                    <h3 className="text-lg font-semibold text-slate-900">Resultado da importação</h3>
                    <p className="text-sm text-slate-500">Relatório por linha e histórico atualizado.</p>
                  </div>
                </div>

                <Alert>
                  <AlertTitle>Resumo final</AlertTitle>
                  <AlertDescription>
                    <div className="space-y-2">
                      <p>Importação processada com sucesso.</p>
                      <ul className="list-disc pl-5 space-y-1">
                        <li>Casos: {commitResult?.totals?.cases || 0}</li>
                        <li>Acordos: {commitResult?.totals?.agreements || 0}</li>
                        <li>Parcelas: {commitResult?.totals?.installments || 0}</li>
                        <li>Alvarás: {commitResult?.totals?.alvaras || 0}</li>
                      </ul>
                    </div>
                  </AlertDescription>
                </Alert>

                <div className="rounded-lg border border-slate-200 overflow-x-auto">
                  <table className="min-w-full text-sm">
                    <thead className="bg-slate-100">
                      <tr>
                        <th className="px-4 py-2 text-left text-slate-600 font-medium">Linha</th>
                        <th className="px-4 py-2 text-left text-slate-600 font-medium">Status</th>
                        <th className="px-4 py-2 text-left text-slate-600 font-medium">Mensagem</th>
                      </tr>
                    </thead>
                    <tbody>
                      {importResults.map((result) => (
                        <tr key={`result-${result.row}`} className="border-t border-slate-100">
                          <td className="px-4 py-2 text-slate-700">{result.row}</td>
                          <td className="px-4 py-2 text-emerald-600 font-medium">{result.status}</td>
                          <td className="px-4 py-2 text-slate-700">{result.message}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <div className="flex gap-3">
                  <Button variant="outline" onClick={resetWizard}>
                    Nova importação
                  </Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Histórico recente</CardTitle>
            <CardDescription>Registros das últimas importações realizadas.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {history.length === 0 && (
              <div className="flex items-center gap-2 text-sm text-slate-500">
                <AlertTriangle className="w-4 h-4" />
                Nenhuma importação registrada ainda.
              </div>
            )}
            {history.length > 0 && (
              <div className="space-y-3">
                {history.map((entry) => (
                  <div key={entry.id} className="border border-slate-200 rounded-lg p-4">
                    <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-2">
                      <div>
                        <p className="text-sm font-semibold text-slate-900">{entry.filename}</p>
                        <p className="text-xs text-slate-500">{new Date(entry.created_at).toLocaleString()}</p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <Badge variant="outline">Casos: {entry.totals?.cases || 0}</Badge>
                        <Badge variant="outline">Acordos: {entry.totals?.agreements || 0}</Badge>
                        <Badge variant="outline">Parcelas: {entry.totals?.installments || 0}</Badge>
                        <Badge variant="outline">Alvarás: {entry.totals?.alvaras || 0}</Badge>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <div className="flex justify-end">
          <Button variant="ghost" onClick={resetWizard}>
            Reiniciar wizard
          </Button>
        </div>
      </main>
    </div>
  );
}
