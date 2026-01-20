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
