from fastapi import FastAPI, APIRouter, HTTPException, Depends, status, UploadFile, File
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
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

security = HTTPBearer()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid authentication")
        user = await db.users.find_one({"id": user_id}, {"_id": 0})
        if user is None:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid authentication")


class UserRegister(BaseModel):
    email: EmailStr
    password: str
    full_name: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: EmailStr
    full_name: str
    role: str = "user"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CaseCreate(BaseModel):
    debtor_name: str
    internal_id: Optional[str] = None
    value_causa: float
    has_agreement: bool = False
    polo_ativo_text: str
    notes: Optional[str] = None
    numero_processo: Optional[str] = None
    data_protocolo: Optional[str] = None
    status_processo: Optional[str] = None
    data_matricula: Optional[str] = None
    cpf: Optional[str] = None
    curso: Optional[str] = None


class CaseUpdate(BaseModel):
    debtor_name: Optional[str] = None
    internal_id: Optional[str] = None
    value_causa: Optional[float] = None
    has_agreement: Optional[bool] = None
    polo_ativo_text: Optional[str] = None
    notes: Optional[str] = None
    numero_processo: Optional[str] = None
    data_protocolo: Optional[str] = None
    status_processo: Optional[str] = None
    data_matricula: Optional[str] = None
    cpf: Optional[str] = None
    curso: Optional[str] = None


class Case(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    debtor_name: str
    internal_id: Optional[str] = None
    value_causa: float
    has_agreement: bool = False
    polo_ativo_text: str
    polo_ativo_codigo: Optional[str] = None
    notes: Optional[str] = None
    numero_processo: Optional[str] = None
    data_protocolo: Optional[str] = None
    status_processo: Optional[str] = None
    data_matricula: Optional[str] = None
    cpf: Optional[str] = None
    curso: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    user_id: str


class AgreementCreate(BaseModel):
    case_id: str
    total_value: float
    installments_count: int
    installment_value: float
    first_due_date: str
    has_entry: bool = False
    entry_value: Optional[float] = None
    entry_via_alvara: bool = False
    entry_date: Optional[str] = None


class Agreement(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    case_id: str
    total_value: float
    installments_count: int
    installment_value: float
    first_due_date: str
    has_entry: bool = False
    entry_value: Optional[float] = None
    entry_via_alvara: bool = False
    entry_date: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class InstallmentUpdate(BaseModel):
    paid_date: Optional[str] = None
    paid_value: Optional[float] = None
    due_date: Optional[str] = None


class Installment(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agreement_id: str
    number: int
    due_date: str
    paid_date: Optional[str] = None
    paid_value: Optional[float] = None
    status_calc: str = "pending"
    is_entry: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AlvaraCreate(BaseModel):
    case_id: str
    data_alvara: Optional[str] = None
    valor_alvara: float
    beneficiario_codigo: str
    observacoes: Optional[str] = None
    status_alvara: str = "Aguardando alvará"


class AlvaraUpdate(BaseModel):
    data_alvara: Optional[str] = None
    valor_alvara: Optional[float] = None
    beneficiario_codigo: Optional[str] = None
    observacoes: Optional[str] = None
    status_alvara: Optional[str] = None


class Alvara(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    case_id: str
    data_alvara: Optional[str] = None
    valor_alvara: float
    beneficiario_codigo: str
    observacoes: Optional[str] = None
    status_alvara: str = "Aguardando alvará"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def extract_beneficiary_code(text: str) -> Optional[str]:
    if "31" in text:
        return "31"
    elif "14" in text:
        return "14"
    return None


def calculate_installment_status(due_date_str: str, paid_date: Optional[str]) -> str:
    if paid_date:
        return "Pago"
    
    try:
        due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date()
        today = datetime.now(timezone.utc).date()
        diff = (due_date - today).days
        
        if 1 <= diff <= 5:
            return "Pagamento próximo"
        elif diff == 0:
            return "Dia de pagamento"
        elif -10 <= diff <= -1:
            return "Atrasado"
        elif diff < -10:
            return "Descumprido"
        else:
            return "Pendente"
    except:
        return "Pendente"


async def calculate_case_total_received(case_id: str) -> float:
    total = 0.0
    
    # Soma de parcelas pagas (incluindo entrada não-alvará)
    installments = await db.installments.find({"paid_date": {"$ne": None}}, {"_id": 0}).to_list(1000)
    for inst in installments:
        agreement = await db.agreements.find_one({"id": inst["agreement_id"]}, {"_id": 0})
        if agreement and agreement["case_id"] == case_id:
            total += inst.get("paid_value", 0)
    
    # Soma de alvarás PAGOS apenas
    alvaras = await db.alvaras.find({"case_id": case_id, "status_alvara": "Alvará pago"}, {"_id": 0}).to_list(1000)
    for alvara in alvaras:
        total += alvara.get("valor_alvara", 0)
    
    return total


@api_router.post("/auth/register")
async def register(user_data: UserRegister):
    existing_user = await db.users.find_one({"email": user_data.email}, {"_id": 0})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    user = User(
        email=user_data.email,
        full_name=user_data.full_name
    )
    
    doc = user.model_dump()
    doc["password"] = hash_password(user_data.password)
    doc["created_at"] = doc["created_at"].isoformat()
    
    await db.users.insert_one(doc)
    
    token = create_access_token({"sub": user.id})
    return {"token": token, "user": user}


@api_router.post("/auth/login")
async def login(credentials: UserLogin):
    user = await db.users.find_one({"email": credentials.email}, {"_id": 0})
    if not user or not verify_password(credentials.password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_access_token({"sub": user["id"]})
    user_obj = User(**user)
    return {"token": token, "user": user_obj}


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
    current_user: dict = Depends(get_current_user)
):
    query = {"user_id": current_user["id"]}
    
    if search:
        query["debtor_name"] = {"$regex": search, "$options": "i"}
    if has_agreement is not None:
        query["has_agreement"] = has_agreement
    if beneficiario:
        query["polo_ativo_codigo"] = beneficiario
    if status_processo:
        query["status_processo"] = status_processo
    
    cases = await db.cases.find(query, {"_id": 0}).to_list(1000)
    
    result = []
    for case in cases:
        case_id = case["id"]
        
        total_received = await calculate_case_total_received(case_id)
        percent_recovered = (total_received / case["value_causa"] * 100) if case["value_causa"] > 0 else 0
        
        agreement = await db.agreements.find_one({"case_id": case_id}, {"_id": 0})
        status_do_acordo = ""
        
        if case.get("has_agreement") and agreement:
            installments_list = await db.installments.find({"agreement_id": agreement["id"]}, {"_id": 0}).to_list(1000)
            
            for inst in installments_list:
                inst["status_calc"] = calculate_installment_status(inst["due_date"], inst.get("paid_date"))
            
            pending_count = sum(1 for i in installments_list if i["status_calc"] != "Pago")
            has_descumprido = any(i["status_calc"] == "Descumprido" for i in installments_list)
            has_atrasado = any(i["status_calc"] == "Atrasado" for i in installments_list)
            has_dia_pagamento = any(i["status_calc"] == "Dia de pagamento" for i in installments_list)
            
            if pending_count == 0:
                status_do_acordo = "Quitado"
                # Verificar situação de alvará antes de marcar sucesso
                alvaras_case = await db.alvaras.find({"case_id": case_id}, {"_id": 0}).to_list(1000)
                has_pending_alvara = any(a.get("status_alvara") == "Aguardando alvará" for a in alvaras_case)
                has_paid_alvara = any(a.get("status_alvara") == "Alvará pago" for a in alvaras_case)

                if has_pending_alvara:
                    await db.cases.update_one({"id": case_id}, {"$set": {"status_processo": "Aguardando alvará"}})
                    case["status_processo"] = "Aguardando alvará"
                elif has_paid_alvara or not alvaras_case:
                    await db.cases.update_one({"id": case_id}, {"$set": {"status_processo": "Sucesso"}})
                    case["status_processo"] = "Sucesso"
            elif has_descumprido:
                status_do_acordo = "Descumprido"
            elif has_atrasado:
                status_do_acordo = "Em atraso"
            elif has_dia_pagamento:
                status_do_acordo = "Dia de pagamento"
            else:
                status_do_acordo = "Em andamento"
        
        if status_acordo and status_do_acordo != status_acordo:
            continue
        
        result.append({
            **case,
            "total_received": total_received,
            "percent_recovered": round(percent_recovered, 2),
            "status_acordo": status_do_acordo
        })
    
    return result


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
        "alvaras": alvaras,
        "total_received": total_received,
        "percent_recovered": round(percent_recovered, 2)
    }


@api_router.put("/cases/{case_id}")
async def update_case(case_id: str, case_data: CaseUpdate, current_user: dict = Depends(get_current_user)):
    case = await db.cases.find_one({"id": case_id, "user_id": current_user["id"]}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    update_data = {k: v for k, v in case_data.model_dump().items() if v is not None}
    
    if "polo_ativo_text" in update_data:
        update_data["polo_ativo_codigo"] = extract_beneficiary_code(update_data["polo_ativo_text"])
    
    if update_data:
        await db.cases.update_one({"id": case_id}, {"$set": update_data})
    
    updated_case = await db.cases.find_one({"id": case_id}, {"_id": 0})
    return updated_case


@api_router.delete("/cases/{case_id}")
async def delete_case(case_id: str, current_user: dict = Depends(get_current_user)):
    case = await db.cases.find_one({"id": case_id, "user_id": current_user["id"]}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    # Excluir agreement e installments
    agreement = await db.agreements.find_one({"case_id": case_id}, {"_id": 0})
    if agreement:
        await db.installments.delete_many({"agreement_id": agreement["id"]})
        await db.agreements.delete_one({"id": agreement["id"]})
    
    # Excluir alvarás
    await db.alvaras.delete_many({"case_id": case_id})
    
    # Excluir caso
    await db.cases.delete_one({"id": case_id})
    return {"message": "Case deleted successfully"}


@api_router.post("/agreements", response_model=Agreement)
async def create_agreement(agreement_data: AgreementCreate, current_user: dict = Depends(get_current_user)):
    case = await db.cases.find_one({"id": agreement_data.case_id, "user_id": current_user["id"]}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    existing_agreement = await db.agreements.find_one({"case_id": agreement_data.case_id}, {"_id": 0})
    if existing_agreement:
        raise HTTPException(status_code=400, detail="Agreement already exists for this case")
    
    agreement = Agreement(**agreement_data.model_dump())
    doc = agreement.model_dump()
    doc["created_at"] = doc["created_at"].isoformat()
    await db.agreements.insert_one(doc)
    
    # Se entrada NÃO via alvará, criar parcela especial #0 (Entrada) SEMPRE EM ABERTO
    if agreement_data.has_entry and not agreement_data.entry_via_alvara:
        entry_installment = Installment(
            agreement_id=agreement.id,
            number=0,
            due_date=agreement_data.entry_date or agreement_data.first_due_date,
            paid_date=None,  # SEMPRE NONE - usuário deve marcar manualmente
            paid_value=None,  # SEMPRE NONE - usuário deve marcar manualmente
            is_entry=True
        )
        entry_doc = entry_installment.model_dump()
        entry_doc["created_at"] = entry_doc["created_at"].isoformat()
        await db.installments.insert_one(entry_doc)
    
    # Gerar parcelas regulares com 1 MÊS CALENDÁRIO (não 30 dias)
    if agreement_data.has_entry and agreement_data.entry_date:
        entry_date = datetime.strptime(agreement_data.entry_date, "%Y-%m-%d")
        # Adicionar 1 mês calendário
        if entry_date.month == 12:
            first_due = entry_date.replace(year=entry_date.year + 1, month=1)
        else:
            first_due = entry_date.replace(month=entry_date.month + 1)
    else:
        first_due = datetime.strptime(agreement_data.first_due_date, "%Y-%m-%d")
    
    for i in range(agreement_data.installments_count):
        # Adicionar i meses calendário
        year = first_due.year
        month = first_due.month + i
        day = first_due.day
        
        # Ajustar ano e mês se ultrapassar 12
        while month > 12:
            month -= 12
            year += 1
        
        # Tentar criar a data, ajustando o dia se necessário
        try:
            due_date = datetime(year, month, day)
        except ValueError:
            # Dia não existe no mês (ex: 31 em fevereiro), usar último dia do mês
            if month == 12:
                next_month = datetime(year + 1, 1, 1)
            else:
                next_month = datetime(year, month + 1, 1)
            due_date = next_month - timedelta(days=1)
        
        installment = Installment(
            agreement_id=agreement.id,
            number=i + 1,
            due_date=due_date.strftime("%Y-%m-%d"),
            is_entry=False
        )
        inst_doc = installment.model_dump()
        inst_doc["created_at"] = inst_doc["created_at"].isoformat()
        await db.installments.insert_one(inst_doc)
    
    # Se entrada via alvará, criar registro de alvará automaticamente
    if agreement_data.has_entry and agreement_data.entry_via_alvara and agreement_data.entry_value:
        alvara = Alvara(
            case_id=agreement_data.case_id,
            data_alvara=agreement_data.entry_date,  # Pode ser None
            valor_alvara=agreement_data.entry_value,
            beneficiario_codigo=case.get("polo_ativo_codigo", "31"),
            observacoes="Entrada via Alvará Judicial",
            status_alvara="Aguardando alvará"
        )
        alvara_doc = alvara.model_dump()
        alvara_doc["created_at"] = alvara_doc["created_at"].isoformat()
        await db.alvaras.insert_one(alvara_doc)
    
    # Atualizar caso: has_agreement = True e status_processo = "Acordo"
    await db.cases.update_one(
        {"id": agreement_data.case_id},
        {"$set": {"has_agreement": True, "status_processo": "Acordo"}}
    )
    
    return agreement


@api_router.delete("/agreements/{agreement_id}")
async def delete_agreement(agreement_id: str, current_user: dict = Depends(get_current_user)):
    agreement = await db.agreements.find_one({"id": agreement_id}, {"_id": 0})
    if not agreement:
        raise HTTPException(status_code=404, detail="Agreement not found")
    
    # Verificar se o caso pertence ao usuário
    case = await db.cases.find_one({"id": agreement["case_id"], "user_id": current_user["id"]}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    # Verificar se há pagamentos
    paid_installments = await db.installments.find_one({"agreement_id": agreement_id, "paid_date": {"$ne": None}}, {"_id": 0})
    has_payments = paid_installments is not None
    
    # Excluir installments
    await db.installments.delete_many({"agreement_id": agreement_id})
    
    # Excluir agreement
    await db.agreements.delete_one({"id": agreement_id})
    
    # Atualizar caso
    await db.cases.update_one({"id": agreement["case_id"]}, {"$set": {"has_agreement": False}})
    
    return {"message": "Agreement deleted successfully", "has_payments": has_payments}


@api_router.put("/installments/{installment_id}")
async def update_installment(installment_id: str, data: InstallmentUpdate, current_user: dict = Depends(get_current_user)):
    installment = await db.installments.find_one({"id": installment_id}, {"_id": 0})
    if not installment:
        raise HTTPException(status_code=404, detail="Installment not found")
    
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    
    if update_data:
        await db.installments.update_one({"id": installment_id}, {"$set": update_data})
    
    updated = await db.installments.find_one({"id": installment_id}, {"_id": 0})
    updated["status_calc"] = calculate_installment_status(updated["due_date"], updated.get("paid_date"))
    
    return updated


@api_router.post("/alvaras", response_model=Alvara)
async def create_alvara(alvara_data: AlvaraCreate, current_user: dict = Depends(get_current_user)):
    case = await db.cases.find_one({"id": alvara_data.case_id, "user_id": current_user["id"]}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    alvara = Alvara(**alvara_data.model_dump())
    doc = alvara.model_dump()
    doc["created_at"] = doc["created_at"].isoformat()
    await db.alvaras.insert_one(doc)
    
    return alvara


@api_router.get("/alvaras")
async def get_alvaras(case_id: str, current_user: dict = Depends(get_current_user)):
    case = await db.cases.find_one({"id": case_id, "user_id": current_user["id"]}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    alvaras = await db.alvaras.find({"case_id": case_id}, {"_id": 0}).to_list(1000)
    return alvaras


@api_router.put("/alvaras/{alvara_id}")
async def update_alvara(alvara_id: str, alvara_data: AlvaraUpdate, current_user: dict = Depends(get_current_user)):
    alvara = await db.alvaras.find_one({"id": alvara_id}, {"_id": 0})
    if not alvara:
        raise HTTPException(status_code=404, detail="Alvara not found")
    
    update_data = {k: v for k, v in alvara_data.model_dump().items() if v is not None}
    
    if update_data:
        await db.alvaras.update_one({"id": alvara_id}, {"$set": update_data})
    
    updated = await db.alvaras.find_one({"id": alvara_id}, {"_id": 0})
    return updated


@api_router.delete("/alvaras/{alvara_id}")
async def delete_alvara(alvara_id: str, current_user: dict = Depends(get_current_user)):
    alvara = await db.alvaras.find_one({"id": alvara_id}, {"_id": 0})
    if not alvara:
        raise HTTPException(status_code=404, detail="Alvara not found")
    
    await db.alvaras.delete_one({"id": alvara_id})
    return {"message": "Alvara deleted successfully"}


@api_router.get("/receipts/pdf")
async def get_receipts_pdf(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    beneficiario: Optional[str] = None,
    type: Optional[str] = None,
    preset: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    # Chamar o endpoint de receipts para obter os dados
    params = {}
    if start_date: params['start_date'] = start_date
    if end_date: params['end_date'] = end_date
    if beneficiario: params['beneficiario'] = beneficiario
    if type: params['type'] = type
    if preset: params['preset'] = preset
    
    # Obter dados (reutilizar lógica do endpoint get_receipts)
    today = datetime.now(timezone.utc).date()
    
    if preset == "day":
        start_date = today.strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")
        period_text = f"{today.strftime('%d/%m/%Y')}"
    elif preset == "week":
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)
        start_date = start_of_week.strftime("%Y-%m-%d")
        end_date = end_of_week.strftime("%Y-%m-%d")
        period_text = f"{start_of_week.strftime('%d/%m/%Y')} a {end_of_week.strftime('%d/%m/%Y')}"
    elif preset == "month":
        start_of_month = today.replace(day=1)
        if today.month == 12:
            end_of_month = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end_of_month = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        start_date = start_of_month.strftime("%Y-%m-%d")
        end_date = end_of_month.strftime("%Y-%m-%d")
        period_text = f"{start_of_month.strftime('%m/%Y')}"
    elif preset == "year":
        start_of_year = today.replace(month=1, day=1)
        end_of_year = today.replace(month=12, day=31)
        start_date = start_of_year.strftime("%Y-%m-%d")
        end_date = end_of_year.strftime("%Y-%m-%d")
        period_text = f"{start_of_year.strftime('%Y')}"
    else:
        period_text = f"{start_date or 'Início'} a {end_date or 'Fim'}"
    
    receipts = []
    total_received = 0.0
    total_31 = 0.0
    total_14 = 0.0
    total_parcelas = 0.0
    total_alvaras = 0.0
    case_ids_with_receipts = set()
    
    user_cases = await db.cases.find({"user_id": current_user["id"]}, {"_id": 0}).to_list(1000)
    case_map = {c["id"]: c for c in user_cases}
    
    # Parcelas pagas
    if not type or type == "all" or type == "parcelas":
        installments = await db.installments.find({"paid_date": {"$ne": None}}, {"_id": 0}).to_list(10000)
        for inst in installments:
            paid_date = inst.get("paid_date")
            if paid_date and (not start_date or paid_date >= start_date) and (not end_date or paid_date <= end_date):
                agreement = await db.agreements.find_one({"id": inst["agreement_id"]}, {"_id": 0})
                if agreement and agreement["case_id"] in case_map:
                    case = case_map[agreement["case_id"]]
                    beneficiario_codigo = case.get("polo_ativo_codigo")
                    
                    if not beneficiario or beneficiario == "all" or beneficiario_codigo == beneficiario:
                        paid_value = inst.get("paid_value", 0)
                        type_label = "Entrada" if inst.get("is_entry") else "Parcela"
                        receipts.append({
                            "date": paid_date,
                            "case_id": case["id"],
                            "debtor": case["debtor_name"],
                            "numero_processo": case.get("numero_processo", ""),
                            "type": type_label,
                            "value": paid_value,
                            "beneficiario": beneficiario_codigo or "",
                            "observacoes": f"{type_label} #{inst['number']}" if not inst.get("is_entry") else "Entrada do acordo"
                        })
                        total_received += paid_value
                        total_parcelas += paid_value
                        if beneficiario_codigo == "31":
                            total_31 += paid_value
                        elif beneficiario_codigo == "14":
                            total_14 += paid_value
                        case_ids_with_receipts.add(case["id"])
    
    # Alvarás PAGOS
    if not type or type == "all" or type == "alvara":
        alvaras = await db.alvaras.find({"status_alvara": "Alvará pago"}, {"_id": 0}).to_list(10000)
        for alvara in alvaras:
            data_alvara = alvara.get("data_alvara")
            if data_alvara and (not start_date or data_alvara >= start_date) and (not end_date or data_alvara <= end_date):
                if alvara["case_id"] in case_map:
                    case = case_map[alvara["case_id"]]
                    beneficiario_codigo = alvara.get("beneficiario_codigo")
                    
                    if not beneficiario or beneficiario == "all" or beneficiario_codigo == beneficiario:
                        valor_alvara = alvara.get("valor_alvara", 0)
                        receipts.append({
                            "date": data_alvara,
                            "case_id": case["id"],
                            "debtor": case["debtor_name"],
                            "numero_processo": case.get("numero_processo", ""),
                            "type": "Alvará Judicial",
                            "value": valor_alvara,
                            "beneficiario": beneficiario_codigo or "",
                            "observacoes": alvara.get("observacoes", "")
                        })
                        total_received += valor_alvara
                        total_alvaras += valor_alvara
                        if beneficiario_codigo == "31":
                            total_31 += valor_alvara
                        elif beneficiario_codigo == "14":
                            total_14 += valor_alvara
                        case_ids_with_receipts.add(case["id"])
    
    receipts.sort(key=lambda x: x["date"], reverse=True)
    
    data = {
        "receipts": receipts,
        "kpis": {
            "total_received": round(total_received, 2),
            "total_31": round(total_31, 2),
            "total_14": round(total_14, 2),
            "total_parcelas": round(total_parcelas, 2),
            "total_alvaras": round(total_alvaras, 2),
            "cases_with_receipts": len(case_ids_with_receipts)
        }
    }
    
    filters = {
        "period": period_text,
        "beneficiario": beneficiario if beneficiario and beneficiario != "all" else "Todos",
        "type": type if type and type != "all" else "Todos"
    }
    
    pdf_buffer = generate_receipts_pdf(data, filters)
    
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=recebimentos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"}
    )


@api_router.get("/receipts")
async def get_receipts(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    beneficiario: Optional[str] = None,
    type: Optional[str] = None,
    preset: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    today = datetime.now(timezone.utc).date()
    
    if preset == "day":
        start_date = today.strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")
    elif preset == "week":
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)
        start_date = start_of_week.strftime("%Y-%m-%d")
        end_date = end_of_week.strftime("%Y-%m-%d")
    elif preset == "month":
        start_of_month = today.replace(day=1)
        if today.month == 12:
            end_of_month = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end_of_month = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        start_date = start_of_month.strftime("%Y-%m-%d")
        end_date = end_of_month.strftime("%Y-%m-%d")
    elif preset == "year":
        start_of_year = today.replace(month=1, day=1)
        end_of_year = today.replace(month=12, day=31)
        start_date = start_of_year.strftime("%Y-%m-%d")
        end_date = end_of_year.strftime("%Y-%m-%d")
    
    receipts = []
    total_received = 0.0
    total_31 = 0.0
    total_14 = 0.0
    total_parcelas = 0.0
    total_alvaras = 0.0
    case_ids_with_receipts = set()
    
    user_cases = await db.cases.find({"user_id": current_user["id"]}, {"_id": 0}).to_list(1000)
    case_map = {c["id"]: c for c in user_cases}
    
    # Parcelas pagas
    if not type or type == "all" or type == "parcelas":
        installments = await db.installments.find({"paid_date": {"$ne": None}}, {"_id": 0}).to_list(10000)
        for inst in installments:
            paid_date = inst.get("paid_date")
            if paid_date and (not start_date or paid_date >= start_date) and (not end_date or paid_date <= end_date):
                agreement = await db.agreements.find_one({"id": inst["agreement_id"]}, {"_id": 0})
                if agreement and agreement["case_id"] in case_map:
                    case = case_map[agreement["case_id"]]
                    beneficiario_codigo = case.get("polo_ativo_codigo")
                    
                    if not beneficiario or beneficiario == "all" or beneficiario_codigo == beneficiario:
                        paid_value = inst.get("paid_value", 0)
                        type_label = "Entrada" if inst.get("is_entry") else "Parcela"
                        receipts.append({
                            "date": paid_date,
                            "case_id": case["id"],
                            "debtor": case["debtor_name"],
                            "numero_processo": case.get("numero_processo", ""),
                            "type": type_label,
                            "value": paid_value,
                            "beneficiario": beneficiario_codigo or "",
                            "observacoes": f"{type_label} #{inst['number']}" if not inst.get("is_entry") else "Entrada do acordo"
                        })
                        total_received += paid_value
                        total_parcelas += paid_value
                        if beneficiario_codigo == "31":
                            total_31 += paid_value
                        elif beneficiario_codigo == "14":
                            total_14 += paid_value
                        case_ids_with_receipts.add(case["id"])
    
    # Alvarás PAGOS apenas
    if not type or type == "all" or type == "alvara":
        alvaras = await db.alvaras.find({"status_alvara": "Alvará pago"}, {"_id": 0}).to_list(10000)
        for alvara in alvaras:
            data_alvara = alvara.get("data_alvara")
            if data_alvara and (not start_date or data_alvara >= start_date) and (not end_date or data_alvara <= end_date):
                if alvara["case_id"] in case_map:
                    case = case_map[alvara["case_id"]]
                    beneficiario_codigo = alvara.get("beneficiario_codigo")
                    
                    if not beneficiario or beneficiario == "all" or beneficiario_codigo == beneficiario:
                        valor_alvara = alvara.get("valor_alvara", 0)
                        receipts.append({
                            "date": data_alvara,
                            "case_id": case["id"],
                            "debtor": case["debtor_name"],
                            "numero_processo": case.get("numero_processo", ""),
                            "type": "Alvará Judicial",
                            "value": valor_alvara,
                            "beneficiario": beneficiario_codigo or "",
                            "observacoes": alvara.get("observacoes", "")
                        })
                        total_received += valor_alvara
                        total_alvaras += valor_alvara
                        if beneficiario_codigo == "31":
                            total_31 += valor_alvara
                        elif beneficiario_codigo == "14":
                            total_14 += valor_alvara
                        case_ids_with_receipts.add(case["id"])
    
    # Entrada agora é tratada como parcela especial (removido)
    
    receipts.sort(key=lambda x: x["date"], reverse=True)
    
    # Consolidado mensal
    monthly_consolidation = {}
    for receipt in receipts:
        date_obj = datetime.strptime(receipt["date"], "%Y-%m-%d")
        month_key = date_obj.strftime("%Y-%m")
        
        if month_key not in monthly_consolidation:
            monthly_consolidation[month_key] = {
                "month": month_key,
                "total_31": 0.0,
                "total_14": 0.0,
                "total_parcelas": 0.0,
                "total_alvaras": 0.0,
                "total": 0.0
            }
        
        monthly_consolidation[month_key]["total"] += receipt["value"]
        
        if receipt["beneficiario"] == "31":
            monthly_consolidation[month_key]["total_31"] += receipt["value"]
        elif receipt["beneficiario"] == "14":
            monthly_consolidation[month_key]["total_14"] += receipt["value"]
        
        if receipt["type"] in ["Parcela", "Entrada"]:
            monthly_consolidation[month_key]["total_parcelas"] += receipt["value"]
        elif receipt["type"] == "Alvará Judicial":
            monthly_consolidation[month_key]["total_alvaras"] += receipt["value"]
    
    monthly_data = sorted(monthly_consolidation.values(), key=lambda x: x["month"], reverse=True)
    
    return {
        "receipts": receipts,
        "kpis": {
            "total_received": round(total_received, 2),
            "total_31": round(total_31, 2),
            "total_14": round(total_14, 2),
            "total_parcelas": round(total_parcelas, 2),
            "total_alvaras": round(total_alvaras, 2),
            "cases_with_receipts": len(case_ids_with_receipts)
        },
        "monthly_consolidation": monthly_data
    }


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@app.on_event("startup")
async def startup_db():
    await db.cases.create_index("user_id")
    await db.cases.create_index("polo_ativo_codigo")
    await db.cases.create_index("numero_processo")
    await db.cases.create_index("cpf")
    await db.cases.create_index("status_processo")
    await db.agreements.create_index("case_id")
    await db.installments.create_index("agreement_id")
    await db.installments.create_index("due_date")
    await db.installments.create_index("paid_date")
    await db.alvaras.create_index("case_id")
    await db.alvaras.create_index("data_alvara")
    await db.alvaras.create_index("beneficiario_codigo")


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
