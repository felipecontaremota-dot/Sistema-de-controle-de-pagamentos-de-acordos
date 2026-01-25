from fastapi import FastAPI, APIRouter, HTTPException, Depends, status, UploadFile, File
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, EmailStr
from typing import Optional, Any
import uuid
from datetime import datetime, date, timedelta, timezone
from dateutil.relativedelta import relativedelta
from passlib.context import CryptContext
from jose import JWTError, jwt
import pandas as pd
import tempfile
import numpy as np
import json

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

app = FastAPI()
api_router = APIRouter(prefix="/api")
import_router = APIRouter(prefix="/import")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY = os.environ.get("SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7

logger = logging.getLogger("uvicorn")

IMPORT_SESSIONS: dict[str, dict[str, Any]] = {}
MAX_IMPORT_FILE_SIZE_MB = 10
IMPORT_ALLOWED_EXTENSIONS = {".csv", ".xls", ".xlsx"}

IMPORT_REQUIRED_FIELDS: dict[str, list[str]] = {}
IMPORT_ENFORCE_REQUIRED_FIELDS = False

class User(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    role: str
    created_at: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class CaseBase(BaseModel):
    debtor_name: str
    internal_id: str
    value_causa: float
    polo_ativo_text: Optional[str] = ""
    notes: Optional[str] = ""
    numero_processo: Optional[str] = ""
    data_protocolo: Optional[str] = ""
    status_processo: Optional[str] = ""
    data_matricula: Optional[str] = ""
    cpf: Optional[str] = ""
    whatsapp: Optional[str] = ""
    email: Optional[EmailStr] = None    
    curso: Optional[str] = ""


class CaseCreate(CaseBase):
    pass


class CaseUpdate(BaseModel):
    debtor_name: Optional[str] = None
    internal_id: Optional[str] = None
    value_causa: Optional[float] = None
    polo_ativo_text: Optional[str] = None
    notes: Optional[str] = None
    numero_processo: Optional[str] = None
    data_protocolo: Optional[str] = None
    status_processo: Optional[str] = None
    status_acordo: Optional[str] = None    
    data_matricula: Optional[str] = None
    cpf: Optional[str] = None
    whatsapp: Optional[str] = None
    email: Optional[EmailStr] = None    
    curso: Optional[str] = None


class Case(CaseBase):
    id: str
    user_id: str
    has_agreement: bool = False
    polo_ativo_codigo: Optional[str] = None
    created_at: Optional[str] = None
    status_acordo: Optional[str] = ""
    total_received: float = 0.0
    percent_recovered: float = 0.0


class AgreementCreate(BaseModel):
    case_id: str
    total_value: float
    installments_count: int
    installment_value: float
    first_due_date: str
    observation: Optional[str] = None    
    has_entry: Optional[bool] = False
    entry_value: Optional[float] = 0.0
    entry_via_alvara: Optional[bool] = False
    entry_date: Optional[str] = None


class Agreement(BaseModel):
    id: str
    case_id: str
    total_value: float
    installments_count: int
    installment_value: float
    first_due_date: str
    observation: Optional[str] = None
    has_entry: Optional[bool] = False
    entry_value: Optional[float] = 0.0
    entry_via_alvara: Optional[bool] = False
    entry_date: Optional[str] = None
    created_at: Optional[str] = None

class AgreementUpdate(BaseModel):
    total_value: Optional[float] = None
    installments_count: Optional[int] = None
    installment_value: Optional[float] = None
    first_due_date: Optional[str] = None
    observation: Optional[str] = None    
    has_entry: Optional[bool] = None
    entry_value: Optional[float] = None
    entry_via_alvara: Optional[bool] = None
    entry_date: Optional[str] = None

class InstallmentUpdate(BaseModel):
    paid_date: Optional[str] = None
    paid_value: Optional[float] = None


class AlvaraCreate(BaseModel):
    case_id: str
    data_alvara: str
    valor_alvara: float
    beneficiario_codigo: Optional[str] = None
    observacoes: Optional[str] = None
    status_alvara: Optional[str] = None


class AlvaraUpdate(BaseModel):
    data_alvara: Optional[str] = None
    valor_alvara: Optional[float] = None
    beneficiario_codigo: Optional[str] = None
    observacoes: Optional[str] = None
    status_alvara: Optional[str] = None


class ImportPreviewRequest(BaseModel):
    session_id: str
    sample_size: int = 10


class ImportValidateRequest(BaseModel):
    session_id: str
    mapping: dict


class ImportCommitRequest(BaseModel):
    session_id: str
    mapping: dict


class CaseBulkUpdateFields(BaseModel):
    status_processo: Optional[str] = None
    polo_ativo_text: Optional[str] = None
    status_acordo: Optional[str] = None


class CaseBulkUpdateRequest(BaseModel):
    case_ids: list[str]
    updates: CaseBulkUpdateFields


class CaseBulkDeleteRequest(BaseModel):
    case_ids: list[str]


security = HTTPBearer()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        user = await db.users.find_one({"id": user_id}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        return user
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc


def extract_beneficiary_code(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    if "31" in text:
        return "31"
    if "14" in text:
        return "14"
    return None


def calculate_installment_status(due_date_str: str, paid_date: Optional[str]) -> str:
    if paid_date:
        return "Pago"
    due = datetime.strptime(due_date_str, "%Y-%m-%d").date()
    today = date.today()
    if due == today:
        return "Dia de pagamento"
    if due < today:
        if (today - due).days > 30:
            return "Descumprido"
        return "Atrasado"
    return "Pendente"


async def update_case_materialized_fields(case_id: str) -> None:
    case = await db.cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        return

    agreement = await db.agreements.find_one({"case_id": case_id}, {"_id": 0})
    has_agreement = bool(agreement)

    installments = []
    if agreement:
        installments = await db.installments.find({"agreement_id": agreement["id"]}, {"_id": 0}).to_list(1000)
        for inst in installments:
            inst["status_calc"] = calculate_installment_status(inst["due_date"], inst.get("paid_date"))

    alvaras = await db.alvaras.find({"case_id": case_id}, {"_id": 0}).to_list(1000)

    total_received = 0.0
    if agreement:
        for inst in installments:
            if inst.get("paid_date"):
                total_received += inst.get("paid_value", 0.0)

    for alvara in alvaras:
        if alvara.get("status_alvara") == "Alvará pago":
            total_received += alvara.get("valor_alvara", 0.0)

    percent_recovered = 0.0
    if case.get("value_causa"):
        percent_recovered = (total_received / case["value_causa"]) * 100

    status_acordo = ""
    if agreement:
        pending_count = sum(1 for i in installments if i.get("status_calc") != "Pago")
        has_descumprido = any(i.get("status_calc") == "Descumprido" for i in installments)
        has_atrasado = any(i.get("status_calc") == "Atrasado" for i in installments)
        has_dia_pagamento = any(i.get("status_calc") == "Dia de pagamento" for i in installments)

        if pending_count == 0:
            status_acordo = "Quitado"
            has_pending_alvara = any(a.get("status_alvara") == "Aguardando alvará" for a in alvaras)
            has_paid_alvara = any(a.get("status_alvara") == "Alvará pago" for a in alvaras)
            if has_pending_alvara:
                await db.cases.update_one({"id": case_id}, {"$set": {"status_processo": "Aguardando alvará"}})
            elif has_paid_alvara or not alvaras:
                await db.cases.update_one({"id": case_id}, {"$set": {"status_processo": "Sucesso"}})
        elif has_descumprido:
            status_acordo = "Descumprido"
        elif has_atrasado:
            status_acordo = "Em atraso"
        elif has_dia_pagamento:
            status_acordo = "Dia de pagamento"
        else:
            status_acordo = "Em andamento"

    await db.cases.update_one(
        {"id": case_id},
        {
            "$set": {
                "has_agreement": has_agreement,
                "status_acordo": status_acordo,
                "total_received": round(total_received, 2),
                "percent_recovered": round(percent_recovered, 2),
            }
        }
    )


def normalize_import_value(value: Any) -> Any:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    if pd.isna(value):
        return ""
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, np.generic):
        return value.item()
    return value


def parse_date_value(value: Any) -> Optional[str]:
    if value in ("", None):
        return None
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.strftime("%Y-%m-%d")
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.strftime("%Y-%m-%d")


def parse_float_value(value: Any) -> Optional[float]:
    if value in ("", None):
        return None
    if isinstance(value, (int, float, np.number)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(" ", "")
        if cleaned.count(",") == 1 and cleaned.count(".") >= 1:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        elif cleaned.count(",") == 1 and cleaned.count(".") == 0:
            cleaned = cleaned.replace(",", ".")
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def parse_int_value(value: Any) -> Optional[int]:
    float_value = parse_float_value(value)
    if float_value is None:
        return None
    return int(float_value)


def parse_bool_value(value: Any) -> Optional[bool]:
    if value in ("", None):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"sim", "s", "yes", "y", "true", "1"}:
            return True
        if normalized in {"nao", "não", "n", "no", "false", "0"}:
            return False
    return None


def load_import_dataframe(session: dict[str, Any]) -> pd.DataFrame:
    file_path = session["path"]
    extension = session["extension"]
    if extension == ".csv":
        df = pd.read_csv(file_path)
    else:
        df = pd.read_excel(file_path)
    df.columns = [str(col) for col in df.columns]
    return df


def build_mapping_errors(mapping: dict) -> list[dict[str, Any]]:
    if not IMPORT_ENFORCE_REQUIRED_FIELDS:
        return []    
    errors = []
    for section, required_fields in IMPORT_REQUIRED_FIELDS.items():
        for field in required_fields:
            column = mapping.get(section, {}).get(field) if isinstance(mapping.get(section), dict) else None
            if not column:
                errors.append({"row": None, "message": f"Campo obrigatório não mapeado: {section}.{field}"})
    return errors


def get_import_session(session_id: str, user_id: str) -> dict[str, Any]:
    session = IMPORT_SESSIONS.get(session_id)
    if not session or session.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="Sessão de importação não encontrada")
    return session


def build_row_data(df_row: pd.Series, columns: list[str]) -> dict[str, Any]:
    return {column: normalize_import_value(df_row[column]) for column in columns}


def build_row_payload(row: dict[str, Any], mapping_section: dict[str, str]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for field, column in mapping_section.items():
        if column:
            payload[field] = row.get(column, "")
    return payload


@app.on_event("startup")
async def ensure_indexes() -> None:
    await db.cases.create_index([("user_id", 1), ("status_acordo", 1)])
    await db.cases.create_index([("user_id", 1), ("has_agreement", 1)])
    await db.cases.create_index([("user_id", 1), ("created_at", -1)])


@api_router.post("/auth/login")
async def login(credentials: UserLogin):
    user = await db.users.find_one({"email": credentials.email}, {"_id": 0})
    if not user or not verify_password(credentials.password, user.get("password", "")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    access_token = create_access_token({"sub": user["id"]})
    return {"token": access_token}


@api_router.get("/auth/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    return User(**current_user)


@api_router.post("/cases", response_model=Case)
async def create_case(case_data: CaseCreate, current_user: dict = Depends(get_current_user)):
    case = Case(
        **case_data.model_dump(),
        id=str(uuid.uuid4()),
        user_id=current_user["id"],
        created_at=datetime.now(timezone.utc).isoformat(),
        polo_ativo_codigo=extract_beneficiary_code(case_data.polo_ativo_text),
        has_agreement=False,
        status_acordo="",
        total_received=0.0,
        percent_recovered=0.0
    )

    await db.cases.insert_one(case.model_dump())
    return case


@api_router.get("/cases")
async def get_cases(
    search: Optional[str] = None,
    status_acordo: Optional[str] = None,
    has_agreement: Optional[bool] = None,
    beneficiario: Optional[str] = None,
    status_processo: Optional[str] = None,
    page: int = 1,
    limit: int = 10,
    current_user: dict = Depends(get_current_user)
):
    query = {"user_id": current_user["id"]}

    if search:
        query["debtor_name"] = {"$regex": search, "$options": "i"}
    if status_acordo:
        query["status_acordo"] = status_acordo
    if has_agreement is not None:
        query["has_agreement"] = has_agreement
    if beneficiario:
        query["polo_ativo_codigo"] = beneficiario
    if status_processo:
        query["status_processo"] = status_processo

    safe_page = max(page, 1)
    safe_limit = max(limit, 1)
    skip = (safe_page - 1) * safe_limit

    total = await db.cases.count_documents(query)
    cases = await (
        db.cases.find(query, {"_id": 0})
        .sort("created_at", -1)
        .skip(skip)
        .limit(safe_limit)
        .to_list(safe_limit)
    )
    
    result = []
    for case in cases:
        result.append({
            **case,
            "total_received": case.get("total_received", 0.0),
            "percent_recovered": case.get("percent_recovered", 0.0),
            "status_acordo": case.get("status_acordo", "")
        })

    total_pages = max(1, (total + safe_limit - 1) // safe_limit)

    return {
        "data": result,
        "pagination": {
            "page": safe_page,
            "limit": safe_limit,
            "total": total,
            "total_pages": total_pages
        }
    }

@api_router.put("/cases/bulk-update")
async def bulk_update_cases(payload: CaseBulkUpdateRequest, current_user: dict = Depends(get_current_user)):
    if not payload.case_ids:
        raise HTTPException(status_code=400, detail="Nenhum caso selecionado")

    update_data = {k: v for k, v in payload.updates.model_dump().items() if v is not None and v != ""}
    if not update_data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualização")

    if "polo_ativo_text" in update_data:
        update_data["polo_ativo_codigo"] = extract_beneficiary_code(update_data["polo_ativo_text"])

    cases = await db.cases.find(
        {"id": {"$in": payload.case_ids}, "user_id": current_user["id"]},
        {"_id": 0, "id": 1},
    ).to_list(1000)
    case_ids = [case["id"] for case in cases]

    if not case_ids:
        return {"updated": 0}

    await db.cases.update_many({"id": {"$in": case_ids}}, {"$set": update_data})

    for case_id in case_ids:
        await update_case_materialized_fields(case_id)

    if "status_acordo" in update_data:
        for case_id in case_ids:
            agreement = await db.agreements.find_one({"case_id": case_id}, {"_id": 0, "id": 1})
            if not agreement:
                await db.cases.update_one({"id": case_id}, {"$set": {"status_acordo": update_data["status_acordo"]}})

    return {"updated": len(case_ids)}


@api_router.delete("/cases/bulk-delete")
async def bulk_delete_cases(payload: CaseBulkDeleteRequest, current_user: dict = Depends(get_current_user)):
    if not payload.case_ids:
        raise HTTPException(status_code=400, detail="Nenhum caso selecionado")

    cases = await db.cases.find(
        {"id": {"$in": payload.case_ids}, "user_id": current_user["id"]},
        {"_id": 0, "id": 1},
    ).to_list(1000)
    case_ids = [case["id"] for case in cases]

    if not case_ids:
        return {"deleted": 0}

    agreements = await db.agreements.find(
        {"case_id": {"$in": case_ids}},
        {"_id": 0, "id": 1},
    ).to_list(1000)
    agreement_ids = [agreement["id"] for agreement in agreements]

    if agreement_ids:
        await db.installments.delete_many({"agreement_id": {"$in": agreement_ids}})
        await db.agreements.delete_many({"id": {"$in": agreement_ids}})

    await db.alvaras.delete_many({"case_id": {"$in": case_ids}})
    delete_result = await db.cases.delete_many({"id": {"$in": case_ids}, "user_id": current_user["id"]})
    return {"deleted": delete_result.deleted_count}


@api_router.get("/cases/{case_id}")
async def get_case(case_id: str, current_user: dict = Depends(get_current_user)):
    case = await db.cases.find_one({"id": case_id, "user_id": current_user["id"]}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    agreement = await db.agreements.find_one({"case_id": case_id}, {"_id": 0})
    installments = []

    if agreement:
        agreement["observation"] = agreement.get("observation")        
        installments = await db.installments.find({"agreement_id": agreement["id"]}, {"_id": 0}).to_list(1000)
        for inst in installments:
            inst["status_calc"] = calculate_installment_status(inst["due_date"], inst.get("paid_date"))
        installments.sort(key=lambda inst: (not inst.get("is_entry", False), inst.get("number") is None, inst.get("number")))            

    alvaras = await db.alvaras.find({"case_id": case_id}, {"_id": 0}).to_list(1000)

    total_received = case.get("total_received", 0.0)
    percent_recovered = case.get("percent_recovered", 0.0)

    return {
        "case": case,
        "agreement": agreement,
        "installments": installments,
        "alvaras": alvaras,
        "total_received": total_received,
        "percent_recovered": percent_recovered
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

    await update_case_materialized_fields(case_id)
    return await db.cases.find_one({"id": case_id}, {"_id": 0})


@api_router.delete("/cases/{case_id}")
async def delete_case(case_id: str, current_user: dict = Depends(get_current_user)):
    case = await db.cases.find_one({"id": case_id, "user_id": current_user["id"]})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    agreement = await db.agreements.find_one({"case_id": case_id}, {"_id": 0})
    if agreement:
        await db.installments.delete_many({"agreement_id": agreement["id"]})
        await db.agreements.delete_one({"id": agreement["id"]})

    await db.alvaras.delete_many({"case_id": case_id})
    await db.cases.delete_one({"id": case_id})
    return {"message": "Case deleted"}


@api_router.post("/agreements")
async def create_agreement(agreement_data: AgreementCreate, current_user: dict = Depends(get_current_user)):
    case = await db.cases.find_one({"id": agreement_data.case_id, "user_id": current_user["id"]}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    agreement = Agreement(
        id=str(uuid.uuid4()),
        created_at=datetime.now(timezone.utc).isoformat(),
        **agreement_data.model_dump()
    )

    await db.agreements.insert_one(agreement.model_dump())

    # =========================
    # =========================
    # GERAÇÃO DAS PARCELAS
    # =========================

    # 1️⃣ ENTRADA (quando existir e NÃO for via alvará)
    if agreement.has_entry and not agreement.entry_via_alvara:
        entry_installment = {
            "id": str(uuid.uuid4()),
            "agreement_id": agreement.id,
            "is_entry": True,
            "number": None,
            "due_date": agreement.entry_date,
            "paid_date": None,              # 👈 NÃO PAGA
            "paid_value": None,             # 👈 NÃO RECEBIDA
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.installments.insert_one(entry_installment)

    # 2️⃣ PARCELAS MENSAIS (mês calendário)
    first_due = datetime.strptime(agreement.first_due_date, "%Y-%m-%d")

    for i in range(agreement.installments_count):
        due_date = first_due + relativedelta(months=i)

        installment = {
            "id": str(uuid.uuid4()),
            "agreement_id": agreement.id,
            "number": i + 1,
            "is_entry": False,
            "due_date": due_date.strftime("%Y-%m-%d"),
            "paid_date": None,
            "paid_value": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.installments.insert_one(installment)

    # 3️⃣ ENTRADA VIA ALVARÁ (quando aplicável)
    if agreement.has_entry and agreement.entry_via_alvara:
        alvara_entry = {
            "id": str(uuid.uuid4()),
            "case_id": agreement.case_id,
            "data_alvara": agreement.entry_date or datetime.now().strftime("%Y-%m-%d"),
            "valor_alvara": agreement.entry_value or 0.0,
            "beneficiario_codigo": case.get("polo_ativo_codigo"),
            "status_alvara": "Aguardando alvará",
            "observacoes": "Entrada via alvará",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.alvaras.insert_one(alvara_entry)

    await update_case_materialized_fields(agreement.case_id)
    return agreement


@api_router.delete("/agreements/{agreement_id}")
async def delete_agreement(agreement_id: str, current_user: dict = Depends(get_current_user)):
    agreement = await db.agreements.find_one({"id": agreement_id}, {"_id": 0})
    if not agreement:
        raise HTTPException(status_code=404, detail="Agreement not found")

    case = await db.cases.find_one({"id": agreement["case_id"], "user_id": current_user["id"]}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    await db.installments.delete_many({"agreement_id": agreement_id})
    await db.agreements.delete_one({"id": agreement_id})

    await update_case_materialized_fields(agreement["case_id"])
    return {"message": "Agreement deleted"}

@api_router.put("/agreements/{agreement_id}")
async def update_agreement(
    agreement_id: str,
    payload: AgreementUpdate,
    current_user: dict = Depends(get_current_user)
):
    agreement = await db.agreements.find_one({"id": agreement_id}, {"_id": 0})
    if not agreement:
        raise HTTPException(status_code=404, detail="Agreement not found")

    case = await db.cases.find_one(
        {"id": agreement["case_id"], "user_id": current_user["id"]},
        {"_id": 0},
    )
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    update_data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not update_data:
        return {"message": "No changes to update"}

    # Atualiza o acordo
    await db.agreements.update_one({"id": agreement_id}, {"$set": update_data})

    effective_data = {**agreement, **update_data}

    installments = await db.installments.find(
        {"agreement_id": agreement_id}, {"_id": 0}
    ).to_list(1000)

    has_paid_installments = any(inst.get("paid_date") for inst in installments)

    should_recreate_installments = False
    if "installments_count" in update_data or "first_due_date" in update_data:
        if has_paid_installments:
            raise HTTPException(
                status_code=400,
                detail="Não é possível alterar parcelas quando já existem parcelas pagas.",
            )
        should_recreate_installments = True

    if should_recreate_installments:
        try:
            first_due = datetime.strptime(effective_data["first_due_date"], "%Y-%m-%d")
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=400,
                detail="Data da 1ª parcela inválida.",
            ) from exc

        if not effective_data.get("installments_count"):
            raise HTTPException(
                status_code=400,
                detail="Número de parcelas inválido.",
            )

        # Remove apenas parcelas não pagas
        await db.installments.delete_many(
            {"agreement_id": agreement_id, "paid_date": None}
        )

        for i in range(effective_data["installments_count"]):
            due_date = first_due + relativedelta(months=i)
            installment = {
                "id": str(uuid.uuid4()),
                "agreement_id": agreement_id,
                "number": i + 1,
                "is_entry": False,
                "due_date": due_date.strftime("%Y-%m-%d"),
                "paid_date": None,
                "paid_value": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.installments.insert_one(installment)

        if effective_data.get("has_entry"):
            if effective_data.get("entry_via_alvara"):
                # Decisão sensível: removemos apenas a entrada não paga para evitar duplicidade.
                await db.installments.delete_many(
                    {"agreement_id": agreement_id, "is_entry": True, "paid_date": None}
                )
                entry_alvara = await db.alvaras.find_one(
                    {"case_id": agreement["case_id"], "observacoes": "Entrada via alvará"},
                    {"_id": 0},
                )
                if entry_alvara:
                    if entry_alvara.get("status_alvara") != "Alvará pago":
                        alvara_update = {}
                        if effective_data.get("entry_date"):
                            alvara_update["data_alvara"] = effective_data["entry_date"]
                        if effective_data.get("entry_value") is not None:
                            alvara_update["valor_alvara"] = effective_data["entry_value"]
                        if alvara_update:
                            await db.alvaras.update_one({"id": entry_alvara["id"]}, {"$set": alvara_update})
                else:
                    alvara_entry = {
                        "id": str(uuid.uuid4()),
                        "case_id": agreement["case_id"],
                        "data_alvara": effective_data.get("entry_date")
                        or datetime.now().strftime("%Y-%m-%d"),
                        "valor_alvara": effective_data.get("entry_value") or 0.0,
                        "beneficiario_codigo": case.get("polo_ativo_codigo"),
                        "status_alvara": "Aguardando alvará",
                        "observacoes": "Entrada via alvará",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                    await db.alvaras.insert_one(alvara_entry)
            else:
                entry_date = effective_data.get("entry_date")
                if not entry_date:
                    raise HTTPException(
                        status_code=400,
                        detail="Data da entrada é obrigatória quando não há alvará.",
                    )
                entry_installment = await db.installments.find_one(
                    {"agreement_id": agreement_id, "is_entry": True},
                    {"_id": 0},
                )
                if entry_installment:
                    if entry_installment.get("paid_date") is None:
                        await db.installments.update_one(
                            {"id": entry_installment["id"]},
                            {"$set": {"due_date": entry_date}},
                        )
                else:
                    entry_installment = {
                        "id": str(uuid.uuid4()),
                        "agreement_id": agreement_id,
                        "is_entry": True,
                        "number": None,
                        "due_date": entry_date,
                        "paid_date": None,
                        "paid_value": None,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                    await db.installments.insert_one(entry_installment)
        elif update_data.get("has_entry") is False:
            # Decisão sensível: limpamos registros de entrada ainda não pagos quando removidos pelo usuário.
            await db.installments.delete_many(
                {"agreement_id": agreement_id, "is_entry": True, "paid_date": None}
            )
            await db.alvaras.delete_many(
                {
                    "case_id": agreement["case_id"],
                    "observacoes": "Entrada via alvará",
                    "status_alvara": {"$ne": "Alvará pago"},
                }
            )

        await update_case_materialized_fields(agreement["case_id"])

    return {"message": "Agreement updated successfully"}


@api_router.put("/installments/{installment_id}")
async def update_installment(installment_id: str, update_data: InstallmentUpdate, current_user: dict = Depends(get_current_user)):
    installment = await db.installments.find_one({"id": installment_id}, {"_id": 0})
    if not installment:
        raise HTTPException(status_code=404, detail="Installment not found")

    agreement = await db.agreements.find_one({"id": installment["agreement_id"]}, {"_id": 0})
    if not agreement:
        raise HTTPException(status_code=404, detail="Agreement not found")

    case = await db.cases.find_one({"id": agreement["case_id"], "user_id": current_user["id"]}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    update_payload = {k: v for k, v in update_data.model_dump().items() if v is not None}
    if update_payload:
        await db.installments.update_one({"id": installment_id}, {"$set": update_payload})

    updated_installment = await db.installments.find_one({"id": installment_id}, {"_id": 0})
    updated_installment["status_calc"] = calculate_installment_status(
        updated_installment["due_date"],
        updated_installment.get("paid_date")
    )

    await update_case_materialized_fields(agreement["case_id"])
    return updated_installment

@api_router.get("/alvaras")
async def list_alvaras(case_id: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {}
    if case_id:
        query["case_id"] = case_id
    alvaras = await db.alvaras.find(query, {"_id": 0}).to_list(1000)
    return alvaras


@api_router.get("/alvaras/pendentes")
async def list_alvaras_pendentes(current_user: dict = Depends(get_current_user)):
    cases = await db.cases.find(
        {"user_id": current_user["id"]},
        {"_id": 0, "id": 1, "debtor_name": 1, "numero_processo": 1},
    ).to_list(1000)

    case_map = {case["id"]: case for case in cases}
    if not case_map:
        return []

    alvaras = await db.alvaras.find(
        {"case_id": {"$in": list(case_map.keys())}, "status_alvara": "Aguardando alvará"},
        {"_id": 0},
    ).to_list(1000)

    result = []
    for alvara in alvaras:
        case = case_map.get(alvara.get("case_id"))
        if not case:
            continue
        result.append(
            {
                "alvara_id": alvara.get("id"),
                "case_id": alvara.get("case_id"),
                "data": alvara.get("data_alvara"),
                "devedor": case.get("debtor_name", ""),
                "numero_processo": case.get("numero_processo", ""),
                "valor": alvara.get("valor_alvara", 0.0),
                "beneficiario": alvara.get("beneficiario_codigo"),
                "observacoes": alvara.get("observacoes"),
            }
        )

    return result

@api_router.post("/alvaras")
async def create_alvara(
    alvara_data: AlvaraCreate,
    current_user: dict = Depends(get_current_user)
):
    case = None

    if alvara_data.case_id:
        case = await db.cases.find_one(
            {"id": alvara_data.case_id, "user_id": current_user["id"]},
            {"_id": 0}
        )
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")

    alvara = {
        "id": str(uuid.uuid4()),
        **alvara_data.model_dump(),
        "user_id": current_user["id"],
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "status": "aguardando"
    }

    await db.alvaras.insert_one(alvara)

    if alvara_data.case_id:
        try:
            await update_case_materialized_fields(alvara_data.case_id)
        except Exception:
            pass  # evita erro 500 por falha secundária

    return {
        "message": "Alvará cadastrado com sucesso",
        "id": alvara["id"]
    }


@api_router.put("/alvaras/{alvara_id}")
async def update_alvara(alvara_id: str, alvara_data: AlvaraUpdate, current_user: dict = Depends(get_current_user)):
    alvara = await db.alvaras.find_one({"id": alvara_id}, {"_id": 0})
    if not alvara:
        raise HTTPException(status_code=404, detail="Alvará not found")

    case = await db.cases.find_one({"id": alvara["case_id"], "user_id": current_user["id"]}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    update_payload = {k: v for k, v in alvara_data.model_dump().items() if v is not None}
    if update_payload:
        await db.alvaras.update_one({"id": alvara_id}, {"$set": update_payload})

    await update_case_materialized_fields(alvara["case_id"])
    return await db.alvaras.find_one({"id": alvara_id}, {"_id": 0})


@api_router.delete("/alvaras/{alvara_id}")
async def delete_alvara(alvara_id: str, current_user: dict = Depends(get_current_user)):
    alvara = await db.alvaras.find_one({"id": alvara_id}, {"_id": 0})
    if not alvara:
        raise HTTPException(status_code=404, detail="Alvará not found")

    case = await db.cases.find_one({"id": alvara["case_id"], "user_id": current_user["id"]}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    await db.alvaras.delete_one({"id": alvara_id})
    await update_case_materialized_fields(alvara["case_id"])
    return {"message": "Alvará deleted"}

@api_router.get("/receipts")
async def get_receipts_optimized(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    beneficiario: Optional[str] = None,
    type: Optional[str] = None,
    preset: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    today = datetime.now(timezone.utc).date()

    if preset == "day":
        start_date = end_date = today.strftime("%Y-%m-%d")
    elif preset == "week":
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
        start_date, end_date = start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
    elif preset == "month":
        start = today.replace(day=1)
        end = (start.replace(month=start.month % 12 + 1, day=1) - timedelta(days=1))
        start_date, end_date = start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
    elif preset == "year":
        start_date = today.replace(month=1, day=1).strftime("%Y-%m-%d")
        end_date = today.replace(month=12, day=31).strftime("%Y-%m-%d")

    receipts = []
    totals = {
        "total_received": 0.0,
        "total_31": 0.0,
        "total_14": 0.0,
        "total_parcelas": 0.0,
        "total_alvaras": 0.0,
    }
    case_ids = set()

    cases = await db.cases.find(
        {"user_id": current_user["id"]},
        {"_id": 0, "id": 1, "debtor_name": 1, "numero_processo": 1, "polo_ativo_codigo": 1},
    ).to_list(None)
    case_map = {c["id"]: c for c in cases}

    # Parcelas pagas
    if type in (None, "all", "parcelas"):
        installments = await db.installments.find(
            {"paid_date": {"$ne": None}}, {"_id": 0}
        ).to_list(None)

        for inst in installments:
            paid_date = inst.get("paid_date")
            if not paid_date or not (start_date <= paid_date <= end_date):
                continue

            agreement = await db.agreements.find_one(
                {"id": inst["agreement_id"]}, {"_id": 0, "case_id": 1}
            )
            if not agreement or agreement["case_id"] not in case_map:
                continue

            case = case_map[agreement["case_id"]]
            beneficiario_codigo = case.get("polo_ativo_codigo")

            if beneficiario not in (None, "all", beneficiario_codigo):
                continue

            value = inst.get("paid_value", 0.0)
            label = "Entrada" if inst.get("is_entry") else "Parcela"

            receipts.append({
                "date": paid_date,
                "case_id": case["id"],
                "debtor": case["debtor_name"],
                "numero_processo": case.get("numero_processo", ""),
                "type": label,
                "value": value,
                "beneficiario": beneficiario_codigo,
                "observacoes": f"{label} #{inst.get('number', '')}",
            })

            totals["total_received"] += value
            totals["total_parcelas"] += value
            totals[f"total_{beneficiario_codigo}"] += value if beneficiario_codigo in ("31", "14") else 0
            case_ids.add(case["id"])

    # Alvarás pagos
    if type in (None, "all", "alvara"):
        alvaras = await db.alvaras.find(
            {"status_alvara": "Alvará pago"}, {"_id": 0}
        ).to_list(None)

        for alv in alvaras:
            date = alv.get("data_alvara")
            if not date or not (start_date <= date <= end_date):
                continue

            case = case_map.get(alv["case_id"])
            if not case:
                continue

            beneficiario_codigo = alv.get("beneficiario_codigo")
            if beneficiario not in (None, "all", beneficiario_codigo):
                continue

            value = alv.get("valor_alvara", 0.0)

            receipts.append({
                "date": date,
                "case_id": case["id"],
                "debtor": case["debtor_name"],
                "numero_processo": case.get("numero_processo", ""),
                "type": "Alvará Judicial",
                "value": value,
                "beneficiario": beneficiario_codigo,
                "observacoes": alv.get("observacoes", ""),
            })

            totals["total_received"] += value
            totals["total_alvaras"] += value
            totals[f"total_{beneficiario_codigo}"] += value if beneficiario_codigo in ("31", "14") else 0
            case_ids.add(case["id"])

    receipts.sort(key=lambda r: r["date"], reverse=True)

    return {
        "receipts": receipts,
        "kpis": {**totals, "cases_with_receipts": len(case_ids)},
        "monthly_consolidation": [],
    }


@api_router.get("/receipts/pdf")
async def get_receipts_pdf_optimized(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    beneficiario: Optional[str] = None,
    type: Optional[str] = None,
    preset: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    data = await get_receipts_optimized(
        start_date, end_date, beneficiario, type, preset, current_user
    )

    pdf_buffer = generate_receipts_pdf(
        data,
        {
            "period": preset or "custom",
            "beneficiario": beneficiario or "Todos",
            "type": type or "Todos",
        },
    )

    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=recebimentos.pdf"},
    )


@import_router.post("/upload")
async def upload_import_file(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    filename = file.filename or ""
    extension = Path(filename).suffix.lower()
    if extension not in IMPORT_ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Formato de arquivo não suportado")

    contents = await file.read()
    await file.close()

    if len(contents) > MAX_IMPORT_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Arquivo excede o tamanho permitido")

    with tempfile.NamedTemporaryFile(delete=False, suffix=extension) as temp_file:
        temp_file.write(contents)
        temp_path = temp_file.name

    session_id = str(uuid.uuid4())
    IMPORT_SESSIONS[session_id] = {
        "path": temp_path,
        "filename": filename,
        "extension": extension,
        "user_id": current_user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    return {"session_id": session_id}


@import_router.post("/preview")
async def preview_import_file(
    payload: ImportPreviewRequest,
    current_user: dict = Depends(get_current_user)
):
    session = get_import_session(payload.session_id, current_user["id"])
    df = load_import_dataframe(session)
    columns = df.columns.tolist()
    total_rows = int(len(df.index))
    sample_df = df.head(max(payload.sample_size, 1))
    preview = [build_row_data(row, columns) for _, row in sample_df.iterrows()]

    return {
        "columns": columns,
        "preview": preview,
        "total_rows": total_rows
    }


@import_router.post("/validate")
async def validate_import_file(
    payload: ImportValidateRequest,
    current_user: dict = Depends(get_current_user)
):
    session = get_import_session(payload.session_id, current_user["id"])
    df = load_import_dataframe(session)
    columns = df.columns.tolist()
    mapping = payload.mapping or {}

    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    for index, row in df.iterrows():
        row_data = build_row_data(row, columns)
        case_payload = build_row_payload(row_data, mapping.get("case", {}))
        agreement_payload = build_row_payload(row_data, mapping.get("agreement", {}))
        installment_payload = build_row_payload(row_data, mapping.get("installment", {}))
        alvara_payload = build_row_payload(row_data, mapping.get("alvara", {}))

        if "value_causa" in case_payload and case_payload.get("value_causa") not in ("", None):
            if parse_float_value(case_payload.get("value_causa")) is None:
                warnings.append({"row": index + 1, "message": "Valor da causa inválido"})
        if "total_value" in agreement_payload and agreement_payload.get("total_value") not in ("", None):
            if parse_float_value(agreement_payload.get("total_value")) is None:
                warnings.append({"row": index + 1, "message": "Valor total do acordo inválido"})
        if "installments_count" in agreement_payload and agreement_payload.get("installments_count") not in ("", None):
            if parse_int_value(agreement_payload.get("installments_count")) is None:
                warnings.append({"row": index + 1, "message": "Quantidade de parcelas inválida"})
        if "installment_value" in agreement_payload and agreement_payload.get("installment_value") not in ("", None):
            if parse_float_value(agreement_payload.get("installment_value")) is None:
                warnings.append({"row": index + 1, "message": "Valor da parcela inválida"})
        if "first_due_date" in agreement_payload and agreement_payload.get("first_due_date") not in ("", None):
            if parse_date_value(agreement_payload.get("first_due_date")) is None:
                warnings.append({"row": index + 1, "message": "Primeiro vencimento inválido"})
        value = parse_float_value(agreement_payload.get("total_received_import"))
        if value is not None and value < 0:
            warnings.append({"row": index + 1, "message": "Total recebido inválido"})             
        if "number" in installment_payload and installment_payload.get("number") not in ("", None):
            if parse_int_value(installment_payload.get("number")) is None:
                warnings.append({"row": index + 1, "message": "Número da parcela inválido"})
        if "due_date" in installment_payload and installment_payload.get("due_date") not in ("", None):
            if parse_date_value(installment_payload.get("due_date")) is None:
                warnings.append({"row": index + 1, "message": "Data de vencimento inválida"})
        if "valor_alvara" in alvara_payload and alvara_payload.get("valor_alvara") not in ("", None):
            if parse_float_value(alvara_payload.get("valor_alvara")) is None:
                warnings.append({"row": index + 1, "message": "Valor do alvará inválido"})

    total_rows = int(len(df.index))
    valid_rows = total_rows

    return {
        "summary": {
            "total_rows": total_rows,
            "valid_rows": valid_rows,
            "invalid_rows": 0
        },
        "errors": errors,
        "warnings": warnings
    }


@import_router.post("/commit")
async def commit_import_file(
    payload: ImportCommitRequest,
    current_user: dict = Depends(get_current_user)
):
    session = get_import_session(payload.session_id, current_user["id"])
    df = load_import_dataframe(session)
    columns = df.columns.tolist()
    mapping = payload.mapping or {}

    case_cache: dict[str, dict[str, Any]] = {}
    agreement_cache: dict[str, dict[str, Any]] = {}
    totals = {"cases": 0, "agreements": 0, "installments": 0, "alvaras": 0}
    results: list[dict[str, Any]] = []
    updated_case_ids: set[str] = set()
    total_received_import_values: dict[str, float] = {}    

    for index, row in df.iterrows():
        row_data = build_row_data(row, columns)
        row_number = index + 1

        case_payload = build_row_payload(row_data, mapping.get("case", {}))
        agreement_payload = build_row_payload(row_data, mapping.get("agreement", {}))
        installment_payload = build_row_payload(row_data, mapping.get("installment", {}))
        alvara_payload = build_row_payload(row_data, mapping.get("alvara", {}))

        case_record = None
        has_case_payload = any(value not in ("", None) for value in case_payload.values())
        if has_case_payload:
            case_value_causa = parse_float_value(case_payload.get("value_causa")) or 0.0
            case_internal_id = str(case_payload.get("internal_id") or "").strip()
            case_key = case_internal_id or str(case_payload.get("debtor_name") or "").strip()
            case_cache_key = f"{current_user['id']}::{case_key}" if case_key else None
            if case_cache_key:
                case_record = case_cache.get(case_cache_key)
            if not case_record:
                case_id = str(uuid.uuid4())
                case_record = {
                    "id": case_id,
                    "user_id": current_user["id"],
                    "debtor_name": str(case_payload.get("debtor_name") or ""),
                    "internal_id": case_internal_id or str(uuid.uuid4()),
                    "value_causa": case_value_causa,
                    "polo_ativo_text": str(case_payload.get("polo_ativo_text") or ""),
                    "notes": str(case_payload.get("notes") or ""),
                    "numero_processo": str(case_payload.get("numero_processo") or ""),
                    "data_protocolo": str(case_payload.get("data_protocolo") or ""),
                    "status_processo": str(case_payload.get("status_processo") or ""),
                    "data_matricula": str(case_payload.get("data_matricula") or ""),
                    "cpf": str(case_payload.get("cpf") or ""),
                    "whatsapp": str(case_payload.get("whatsapp") or ""),
                    "email": case_payload.get("email"),
                    "curso": str(case_payload.get("curso") or ""),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "polo_ativo_codigo": extract_beneficiary_code(case_payload.get("polo_ativo_text")),
                    "has_agreement": False,
                    "status_acordo": "",
                    "total_received": 0.0,
                    "percent_recovered": 0.0
                }
                await db.cases.insert_one(case_record)
                if case_cache_key:
                    case_cache[case_cache_key] = case_record
                totals["cases"] += 1

        agreement_record = None
        has_agreement_payload = any(value not in ("", None) for value in agreement_payload.values())
        if case_record and has_agreement_payload:
            agreement_total_value = parse_float_value(agreement_payload.get("total_value")) or 0.0
            agreement_installments_count = parse_int_value(agreement_payload.get("installments_count")) or 0
            agreement_installment_value = parse_float_value(agreement_payload.get("installment_value")) or 0.0
            agreement_first_due = parse_date_value(agreement_payload.get("first_due_date")) or ""
            agreement_key = json.dumps(
                {
                    "case_id": case_record["id"],
                    "total_value": agreement_total_value,
                    "installments_count": agreement_installments_count,
                    "installment_value": agreement_installment_value,
                    "first_due_date": agreement_first_due,
                    "has_entry": parse_bool_value(agreement_payload.get("has_entry")),
                    "entry_value": parse_float_value(agreement_payload.get("entry_value")) or 0.0,
                    "entry_via_alvara": parse_bool_value(agreement_payload.get("entry_via_alvara")) or False,
                    "entry_date": parse_date_value(agreement_payload.get("entry_date")),
                },
                sort_keys=True
            )
            agreement_record = agreement_cache.get(agreement_key)
            if not agreement_record:
                agreement_record = {
                    "id": str(uuid.uuid4()),
                    "case_id": case_record["id"],
                    "total_value": agreement_total_value,
                    "installments_count": agreement_installments_count,
                    "installment_value": agreement_installment_value,
                    "first_due_date": agreement_first_due,
                    "observation": agreement_payload.get("observation"),
                    "has_entry": parse_bool_value(agreement_payload.get("has_entry")) or False,
                    "entry_value": parse_float_value(agreement_payload.get("entry_value")) or 0.0,
                    "entry_via_alvara": parse_bool_value(agreement_payload.get("entry_via_alvara")) or False,
                    "entry_date": parse_date_value(agreement_payload.get("entry_date")),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                await db.agreements.insert_one(agreement_record)
                agreement_cache[agreement_key] = agreement_record
                totals["agreements"] += 1

        has_installment_payload = any(value not in ("", None) for value in installment_payload.values())
        if agreement_record and has_installment_payload:
            installment_record = {
                "id": str(uuid.uuid4()),
                "agreement_id": agreement_record["id"],
                "is_entry": parse_bool_value(installment_payload.get("is_entry")) or False,
                "number": parse_int_value(installment_payload.get("number")),
                "due_date": parse_date_value(installment_payload.get("due_date")) or "",
                "paid_date": parse_date_value(installment_payload.get("paid_date")),
                "paid_value": parse_float_value(installment_payload.get("paid_value")),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.installments.insert_one(installment_record)
            totals["installments"] += 1

        if agreement_record:
            total_received_raw = agreement_payload.get("total_received_import")
            if total_received_raw not in ("", None):
                total_received_value = parse_float_value(total_received_raw)
                if total_received_value is not None and total_received_value > 0:
                    total_received_import_values.setdefault(agreement_record["id"], total_received_value)            

        has_alvara_payload = any(value not in ("", None) for value in alvara_payload.values())
        if case_record and has_alvara_payload:
            alvara_value = parse_float_value(alvara_payload.get("valor_alvara")) or 0.0
            alvara_record = {
                "id": str(uuid.uuid4()),
                "case_id": case_record["id"],
                "data_alvara": parse_date_value(alvara_payload.get("data_alvara")) or "",
                "valor_alvara": alvara_value,
                "beneficiario_codigo": str(alvara_payload.get("beneficiario_codigo") or ""),
                "observacoes": alvara_payload.get("observacoes"),
                "status_alvara": str(alvara_payload.get("status_alvara") or ""),
                "user_id": current_user["id"],
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "status": "aguardando",
            }
            await db.alvaras.insert_one(alvara_record)
            totals["alvaras"] += 1

        if case_record:
            updated_case_ids.add(case_record["id"])
        results.append({
            "row": row_number,
            "status": "Sucesso",
            "message": "Linha processada com sucesso"
        })

    if total_received_import_values:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        for agreement_id, total_received_value in total_received_import_values.items():

            # Garante que o acordo existe
            agreement_exists = await db.agreements.find_one(
                {"id": agreement_id},
                {"_id": 1}
            )

            if not agreement_exists:
                continue

            # Evita duplicação de parcelas
            existing_installment = await db.installments.find_one(
                {"agreement_id": agreement_id},
                {"_id": 1}
            )

            if existing_installment:
                continue

            # Criação segura da parcela automática            
            installment_record = {
                "id": str(uuid.uuid4()),
                "agreement_id": agreement_id,
                "is_entry": False,
                "number": 1,
                "due_date": today,
                "paid_date": today,
                "paid_value": total_received_value,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            
            await db.installments.insert_one(installment_record)
            totals["installments"] += 1
    
    for case_id in updated_case_ids:
        try:
            await update_case_materialized_fields(case_id)
        except Exception:
            pass

    history_entry = {
        "id": str(uuid.uuid4()),
        "user_id": current_user["id"],
        "filename": session.get("filename", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "totals": totals,
    }
    await db.import_history.insert_one(history_entry)

    try:
        os.remove(session["path"])
    except OSError:
        pass
    IMPORT_SESSIONS.pop(payload.session_id, None)

    return {
        "message": "Importação concluída",
        "totals": totals,
        "results": results
    }


@import_router.get("/history")
async def get_import_history(current_user: dict = Depends(get_current_user)):
    history = await db.import_history.find(
        {"user_id": current_user["id"]},
        {"_id": 0, "user_id": 0}
    ).sort("created_at", -1).to_list(50)
    return history


api_router.include_router(import_router)
app.include_router(api_router)
