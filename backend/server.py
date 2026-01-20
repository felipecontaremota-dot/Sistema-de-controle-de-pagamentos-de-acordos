diff --git a/backend/server.py b/backend/server.py
index 410b8ec03da7f313e538914a0e04d712633a6a6c..d35380e17bf19664a89f73caa2f4bba1e0a53dbd 100644
--- a/backend/server.py
+++ b/backend/server.py
@@ -1,33 +1,34 @@
 from fastapi import FastAPI, APIRouter, HTTPException, Depends, status, UploadFile, File
 from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
 from fastapi.responses import StreamingResponse
 from dotenv import load_dotenv
 from starlette.middleware.cors import CORSMiddleware
 from motor.motor_asyncio import AsyncIOMotorClient
 import os
 import logging
+import math
 from pathlib import Path
 from pydantic import BaseModel, Field, ConfigDict, EmailStr
 from typing import List, Optional
 import uuid
 from datetime import datetime, timezone, timedelta
 from passlib.context import CryptContext
 from jose import JWTError, jwt
 import re
 from pdf_generator import generate_receipts_pdf
 
 ROOT_DIR = Path(__file__).parent
 load_dotenv(ROOT_DIR / '.env')
 
 mongo_url = os.environ['MONGO_URL']
 client = AsyncIOMotorClient(mongo_url)
 db = client[os.environ['DB_NAME']]
 
 app = FastAPI()
 api_router = APIRouter(prefix="/api")
 
 pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
 SECRET_KEY = os.environ.get("SECRET_KEY", "your-secret-key-change-in-production")
 ALGORITHM = "HS256"
 ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7
 
@@ -293,119 +294,226 @@ async def login(credentials: UserLogin):
 
 @api_router.get("/auth/me")
 async def get_me(current_user: dict = Depends(get_current_user)):
     return User(**current_user)
 
 
 @api_router.post("/cases", response_model=Case)
 async def create_case(case_data: CaseCreate, current_user: dict = Depends(get_current_user)):
     case = Case(**case_data.model_dump(), user_id=current_user["id"])
     case.polo_ativo_codigo = extract_beneficiary_code(case.polo_ativo_text)
     
     doc = case.model_dump()
     doc["created_at"] = doc["created_at"].isoformat()
     
     await db.cases.insert_one(doc)
     return case
 
 
 @api_router.get("/cases")
 async def get_cases(
     search: Optional[str] = None,
     status_acordo: Optional[str] = None,
     has_agreement: Optional[bool] = None,
     beneficiario: Optional[str] = None,
     status_processo: Optional[str] = None,
+    page: int = 1,
+    limit: int = 10,
     current_user: dict = Depends(get_current_user)
 ):
+    page = max(page, 1)
+    limit = min(max(limit, 1), 100)
+    skip = (page - 1) * limit
+
     query = {"user_id": current_user["id"]}
-    
+
     if search:
         query["debtor_name"] = {"$regex": search, "$options": "i"}
     if has_agreement is not None:
         query["has_agreement"] = has_agreement
     if beneficiario:
         query["polo_ativo_codigo"] = beneficiario
     if status_processo:
         query["status_processo"] = status_processo
-    
-    cases = await db.cases.find(query, {"_id": 0}).to_list(1000)
-    
+
+    async def build_status_map(case_list: List[dict]) -> tuple[dict, dict]:
+        if not case_list:
+            return {}, {}
+
+        case_ids = [case["id"] for case in case_list]
+        agreement_by_case = {}
+        async for agreement in db.agreements.find({"case_id": {"$in": case_ids}}, {"_id": 0}):
+            agreement_by_case[agreement["case_id"]] = agreement
+
+        agreement_ids = [agreement["id"] for agreement in agreement_by_case.values()]
+        installments_by_agreement: dict[str, list] = {}
+        if agreement_ids:
+            async for inst in db.installments.find({"agreement_id": {"$in": agreement_ids}}, {"_id": 0}):
+                inst["status_calc"] = calculate_installment_status(inst["due_date"], inst.get("paid_date"))
+                installments_by_agreement.setdefault(inst["agreement_id"], []).append(inst)
+
+        alvaras_by_case: dict[str, list] = {}
+        async for alvara in db.alvaras.find({"case_id": {"$in": case_ids}}, {"_id": 0}):
+            alvaras_by_case.setdefault(alvara["case_id"], []).append(alvara)
+
+        status_map: dict[str, str] = {}
+        for case in case_list:
+            case_id = case["id"]
+            agreement = agreement_by_case.get(case_id)
+            status_do_acordo = ""
+
+            if case.get("has_agreement") and agreement:
+                installments_list = installments_by_agreement.get(agreement["id"], [])
+
+                pending_count = sum(1 for i in installments_list if i["status_calc"] != "Pago")
+                has_descumprido = any(i["status_calc"] == "Descumprido" for i in installments_list)
+                has_atrasado = any(i["status_calc"] == "Atrasado" for i in installments_list)
+                has_dia_pagamento = any(i["status_calc"] == "Dia de pagamento" for i in installments_list)
+
+                if pending_count == 0:
+                    status_do_acordo = "Quitado"
+                    alvaras_case = alvaras_by_case.get(case_id, [])
+                    has_pending_alvara = any(a.get("status_alvara") == "Aguardando alvará" for a in alvaras_case)
+                    has_paid_alvara = any(a.get("status_alvara") == "Alvará pago" for a in alvaras_case)
+
+                    if has_pending_alvara:
+                        await db.cases.update_one({"id": case_id}, {"$set": {"status_processo": "Aguardando alvará"}})
+                        case["status_processo"] = "Aguardando alvará"
+                    elif has_paid_alvara or not alvaras_case:
+                        await db.cases.update_one({"id": case_id}, {"$set": {"status_processo": "Sucesso"}})
+                        case["status_processo"] = "Sucesso"
+                elif has_descumprido:
+                    status_do_acordo = "Descumprido"
+                elif has_atrasado:
+                    status_do_acordo = "Em atraso"
+                elif has_dia_pagamento:
+                    status_do_acordo = "Dia de pagamento"
+                else:
+                    status_do_acordo = "Em andamento"
+
+            status_map[case_id] = status_do_acordo
+
+        return status_map, agreement_by_case
+
+    if status_acordo:
+        batch_size = max(limit * 2, 50)
+        max_scan = limit * 20
+        max_iterations = 50
+        matched_cases = []
+        status_cache: dict[str, str] = {}
+        agreement_cache: dict[str, dict] = {}
+        total_items = 0
+        cursor_skip = 0
+        iterations = 0
+
+        while (
+            len(matched_cases) < skip + limit
+            and cursor_skip < max_scan
+            and iterations < max_iterations
+        ):
+            base_batch = await db.cases.find(query, {"_id": 0}).skip(cursor_skip).limit(batch_size).to_list(batch_size)
+            if not base_batch:
+                break
+
+            status_map, agreement_by_case = await build_status_map(base_batch)
+            filtered_batch = []
+            for case in base_batch:
+                case_id = case["id"]
+                status_do_acordo = status_map.get(case_id, "")
+                if status_do_acordo == status_acordo:
+                    filtered_batch.append(case)
+                    status_cache[case_id] = status_do_acordo
+                    agreement = agreement_by_case.get(case_id)
+                    if agreement:
+                        agreement_cache[case_id] = agreement
+
+            total_items += len(filtered_batch)
+            matched_cases.extend(filtered_batch)
+            cursor_skip += batch_size
+            iterations += 1
+
+        page_cases = matched_cases[skip:skip + limit]
+        status_map = {case["id"]: status_cache.get(case["id"], "") for case in page_cases}
+        agreement_by_case = {
+            case["id"]: agreement_cache[case["id"]]
+            for case in page_cases
+            if case["id"] in agreement_cache
+        }
+    else:
+        total_items = await db.cases.count_documents(query)
+        page_cases = await db.cases.find(query, {"_id": 0}).skip(skip).limit(limit).to_list(limit)
+        status_map, agreement_by_case = await build_status_map(page_cases)
+
+    total_pages = math.ceil(total_items / limit) if total_items else 0
+
+    case_ids = [case["id"] for case in page_cases]
+    agreement_ids = [
+        agreement_by_case[case_id]["id"]
+        for case_id in case_ids
+        if case_id in agreement_by_case
+    ]
+
+    paid_by_agreement: dict[str, float] = {}
+    if agreement_ids:
+        async for inst in db.installments.find(
+            {"agreement_id": {"$in": agreement_ids}, "paid_date": {"$ne": None}},
+            {"_id": 0}
+        ):
+            paid_by_agreement[inst["agreement_id"]] = paid_by_agreement.get(inst["agreement_id"], 0) + inst.get("paid_value", 0)
+
+    paid_by_case: dict[str, float] = {}
+    if case_ids:
+        async for alvara in db.alvaras.find(
+            {"case_id": {"$in": case_ids}, "status_alvara": "Alvará pago"},
+            {"_id": 0}
+        ):
+            paid_by_case[alvara["case_id"]] = paid_by_case.get(alvara["case_id"], 0) + alvara.get("valor_alvara", 0)
+
     result = []
-    for case in cases:
+    for case in page_cases:
         case_id = case["id"]
-        
-        total_received = await calculate_case_total_received(case_id)
+        agreement = agreement_by_case.get(case_id)
+        total_received = 0.0
+        if agreement:
+            total_received += paid_by_agreement.get(agreement["id"], 0)
+        total_received += paid_by_case.get(case_id, 0)
         percent_recovered = (total_received / case["value_causa"] * 100) if case["value_causa"] > 0 else 0
-        
-        agreement = await db.agreements.find_one({"case_id": case_id}, {"_id": 0})
-        status_do_acordo = ""
-        
-        if case.get("has_agreement") and agreement:
-            installments_list = await db.installments.find({"agreement_id": agreement["id"]}, {"_id": 0}).to_list(1000)
-            
-            for inst in installments_list:
-                inst["status_calc"] = calculate_installment_status(inst["due_date"], inst.get("paid_date"))
-            
-            pending_count = sum(1 for i in installments_list if i["status_calc"] != "Pago")
-            has_descumprido = any(i["status_calc"] == "Descumprido" for i in installments_list)
-            has_atrasado = any(i["status_calc"] == "Atrasado" for i in installments_list)
-            has_dia_pagamento = any(i["status_calc"] == "Dia de pagamento" for i in installments_list)
-            
-            if pending_count == 0:
-                status_do_acordo = "Quitado"
-                # Verificar situação de alvará antes de marcar sucesso
-                alvaras_case = await db.alvaras.find({"case_id": case_id}, {"_id": 0}).to_list(1000)
-                has_pending_alvara = any(a.get("status_alvara") == "Aguardando alvará" for a in alvaras_case)
-                has_paid_alvara = any(a.get("status_alvara") == "Alvará pago" for a in alvaras_case)
-
-                if has_pending_alvara:
-                    await db.cases.update_one({"id": case_id}, {"$set": {"status_processo": "Aguardando alvará"}})
-                    case["status_processo"] = "Aguardando alvará"
-                elif has_paid_alvara or not alvaras_case:
-                    await db.cases.update_one({"id": case_id}, {"$set": {"status_processo": "Sucesso"}})
-                    case["status_processo"] = "Sucesso"
-            elif has_descumprido:
-                status_do_acordo = "Descumprido"
-            elif has_atrasado:
-                status_do_acordo = "Em atraso"
-            elif has_dia_pagamento:
-                status_do_acordo = "Dia de pagamento"
-            else:
-                status_do_acordo = "Em andamento"
-        
-        if status_acordo and status_do_acordo != status_acordo:
-            continue
-        
+
         result.append({
             **case,
             "total_received": total_received,
             "percent_recovered": round(percent_recovered, 2),
-            "status_acordo": status_do_acordo
+            "status_acordo": status_map.get(case_id, "")
         })
-    
-    return result
+
+    return {
+        "items": result,
+        "page": page,
+        "limit": limit,
+        "total_items": total_items,
+        "total_pages": total_pages
+    }
 
 
 @api_router.get("/cases/{case_id}")
 async def get_case(case_id: str, current_user: dict = Depends(get_current_user)):
     case = await db.cases.find_one({"id": case_id, "user_id": current_user["id"]}, {"_id": 0})
     if not case:
         raise HTTPException(status_code=404, detail="Case not found")
     
     agreement = await db.agreements.find_one({"case_id": case_id}, {"_id": 0})
     installments = []
     
     if agreement:
         installments = await db.installments.find({"agreement_id": agreement["id"]}, {"_id": 0}).to_list(1000)
         for inst in installments:
             inst["status_calc"] = calculate_installment_status(inst["due_date"], inst.get("paid_date"))
     
     alvaras = await db.alvaras.find({"case_id": case_id}, {"_id": 0}).to_list(1000)
     
     total_received = await calculate_case_total_received(case_id)
     percent_recovered = (total_received / case["value_causa"] * 100) if case["value_causa"] > 0 else 0
     
     return {
         "case": case,
         "agreement": agreement,
         "installments": installments,
diff --git a/frontend/src/pages/Cases.js b/frontend/src/pages/Cases.js
index a4594367423de394eb73664826072bbb12052983..4163361dfbfdab7d8b79708e67b32a60e285488d 100644
--- a/frontend/src/pages/Cases.js
+++ b/frontend/src/pages/Cases.js
@@ -7,103 +7,115 @@ import { Input } from '../components/ui/input';
 import { Badge } from '../components/ui/badge';
 import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '../components/ui/dialog';
 import { Label } from '../components/ui/label';
 import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
 import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '../components/ui/alert-dialog';
 import { toast } from 'sonner';
 import { Plus, Search, LogOut, Scale, Filter, DollarSign, Trash2 } from 'lucide-react';
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
 
 export default function Cases({ token, setToken }) {
   const [cases, setCases] = useState([]);
   const [search, setSearch] = useState('');
   const [statusFilter, setStatusFilter] = useState('');
   const [beneficiaryFilter, setBeneficiaryFilter] = useState('');
   const [statusProcessoFilter, setStatusProcessoFilter] = useState('');
+  const [page, setPage] = useState(1);
+  const [limit, setLimit] = useState(10);
+  const [totalItems, setTotalItems] = useState(0);
+  const [totalPages, setTotalPages] = useState(0);
+  const [casesLoading, setCasesLoading] = useState(false);
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
+    setCasesLoading(true);
     try {
       const params = new URLSearchParams();
       if (search) params.append('search', search);
       if (statusFilter && statusFilter !== 'all') params.append('status_acordo', statusFilter);
       if (beneficiaryFilter && beneficiaryFilter !== 'all') params.append('beneficiario', beneficiaryFilter);
       if (statusProcessoFilter && statusProcessoFilter !== 'all') params.append('status_processo', statusProcessoFilter);
+      params.append('page', page);
+      params.append('limit', limit);
 
       const response = await api.get(`/cases?${params.toString()}`, {
         headers: { Authorization: `Bearer ${token}` },
       });
 
-      setCases(response.data);
+      setCases(response.data.items || []);
+      setTotalItems(response.data.total_items || 0);
+      setTotalPages(response.data.total_pages || 0);
     } catch (error) {
       if (error.response?.status === 401) {
         handleUnauthorized();
       } else {
         toast.error('Erro ao carregar casos');
       }
+    } finally {
+      setCasesLoading(false);
     }
   };
 
   useEffect(() => {
     fetchCases();
     // eslint-disable-next-line react-hooks/exhaustive-deps
-  }, [search, statusFilter, beneficiaryFilter, statusProcessoFilter]);
+  }, [search, statusFilter, beneficiaryFilter, statusProcessoFilter, page, limit]);
 
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
@@ -186,50 +198,83 @@ export default function Cases({ token, setToken }) {
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
 
+  const handleSearchChange = (event) => {
+    setSearch(event.target.value);
+    setPage(1);
+  };
+
+  const handleStatusFilterChange = (value) => {
+    setStatusFilter(value);
+    setPage(1);
+  };
+
+  const handleBeneficiaryFilterChange = (value) => {
+    setBeneficiaryFilter(value);
+    setPage(1);
+  };
+
+  const handleStatusProcessoFilterChange = (value) => {
+    setStatusProcessoFilter(value);
+    setPage(1);
+  };
+
+  const handleLimitChange = (value) => {
+    setLimit(Number(value));
+    setPage(1);
+  };
+
+  const getPaginationItems = () => {
+    if (totalPages <= 1) return [1];
+    if (totalPages <= 7) return Array.from({ length: totalPages }, (_, index) => index + 1);
+
+    const pages = new Set([1, totalPages, page - 1, page, page + 1].filter((p) => p > 0 && p <= totalPages));
+    return Array.from(pages).sort((a, b) => a - b);
+  };
+
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
                 onClick={handleLogout}
                 variant="ghost"
                 className="hover:bg-slate-100"
                 data-testid="logout-button"
               >
@@ -413,143 +458,172 @@ export default function Cases({ token, setToken }) {
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
 
             <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
               <div>
                 <Label htmlFor="search">Buscar por devedor</Label>
                 <div className="relative mt-1">
                   <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-slate-400" />
                   <Input
                     id="search"
                     value={search}
-                    onChange={(e) => setSearch(e.target.value)}
+                    onChange={handleSearchChange}
                     placeholder="Nome do devedor..."
                     className="pl-10"
                     data-testid="search-input"
                   />
                 </div>
               </div>
 
               <div>
                 <Label htmlFor="status-filter">Status do acordo</Label>
-                <Select value={statusFilter || undefined} onValueChange={setStatusFilter}>
+                <Select value={statusFilter || undefined} onValueChange={handleStatusFilterChange}>
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
-                <Select value={beneficiaryFilter || undefined} onValueChange={setBeneficiaryFilter}>
+                <Select value={beneficiaryFilter || undefined} onValueChange={handleBeneficiaryFilterChange}>
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
-                <Select value={statusProcessoFilter || undefined} onValueChange={setStatusProcessoFilter}>
+                <Select value={statusProcessoFilter || undefined} onValueChange={handleStatusProcessoFilterChange}>
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
             </div>
           </div>
         </div>
 
         <div className="bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden">
+          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 px-6 py-4 border-b border-slate-200">
+            <div className="text-sm text-slate-600">
+              Total: <span className="font-semibold text-slate-900">{totalItems}</span> casos •{' '}
+              <span className="font-semibold text-slate-900">{totalPages}</span> páginas
+            </div>
+            <div className="flex items-center gap-3">
+              <Label htmlFor="limit-select" className="text-sm text-slate-600">
+                Itens por página
+              </Label>
+              <Select value={String(limit)} onValueChange={handleLimitChange}>
+                <SelectTrigger className="w-[120px]" data-testid="limit-select">
+                  <SelectValue />
+                </SelectTrigger>
+                <SelectContent>
+                  <SelectItem value="10">10</SelectItem>
+                  <SelectItem value="20">20</SelectItem>
+                  <SelectItem value="50">50</SelectItem>
+                  <SelectItem value="100">100</SelectItem>
+                </SelectContent>
+              </Select>
+            </div>
+          </div>
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
-                {cases.map((case_) => (
+                {casesLoading ? (
+                  <tr>
+                    <td colSpan={8} className="px-6 py-10 text-center text-slate-500">
+                      Carregando casos...
+                    </td>
+                  </tr>
+                ) : (
+                  cases.map((case_) => (
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
@@ -605,59 +679,105 @@ export default function Cases({ token, setToken }) {
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
-                ))}
+                  ))
+                )}
               </tbody>
             </table>
           </div>
 
-          {cases.length === 0 && (
+          {!casesLoading && cases.length === 0 && (
             <div className="text-center py-12" data-testid="empty-state">
               <p className="text-slate-500">Nenhum caso encontrado</p>
             </div>
           )}
+
+          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 px-6 py-4 border-t border-slate-200">
+            <div className="text-sm text-slate-600">
+              Página <span className="font-semibold text-slate-900">{page}</span> de{' '}
+              <span className="font-semibold text-slate-900">{totalPages || 1}</span>
+            </div>
+            <div className="flex items-center gap-2">
+              <Button
+                variant="outline"
+                size="sm"
+                onClick={() => setPage((prev) => Math.max(prev - 1, 1))}
+                disabled={page <= 1 || casesLoading}
+                data-testid="pagination-prev"
+              >
+                Anterior
+              </Button>
+              {getPaginationItems().map((item, index, array) => {
+                const showEllipsis = index > 0 && item - array[index - 1] > 1;
+                return (
+                  <div key={item} className="flex items-center gap-2">
+                    {showEllipsis && <span className="text-slate-400">...</span>}
+                    <Button
+                      variant={item === page ? 'default' : 'outline'}
+                      size="sm"
+                      onClick={() => setPage(item)}
+                      disabled={casesLoading}
+                      data-testid={`pagination-page-${item}`}
+                      className={item === page ? 'bg-slate-900 text-white' : ''}
+                    >
+                      {item}
+                    </Button>
+                  </div>
+                );
+              })}
+              <Button
+                variant="outline"
+                size="sm"
+                onClick={() => setPage((prev) => Math.min(prev + 1, totalPages || 1))}
+                disabled={page >= totalPages || casesLoading}
+                data-testid="pagination-next"
+              >
+                Próxima
+              </Button>
+            </div>
+          </div>
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
