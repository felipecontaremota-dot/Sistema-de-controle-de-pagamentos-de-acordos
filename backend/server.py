from fastapi import FastAPI, APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, EmailStr
from typing import Optional
import uuid
from datetime import datetime, date, timedelta, timezone
from dateutil.relativedelta import relativedelta
from passlib.context import CryptContext
from jose import JWTError, jwt

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

app = FastAPI()
api_router = APIRouter(prefix="/api")

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
    data_matricula: Optional[str] = None
    cpf: Optional[str] = None
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
    has_entry: Optional[bool] = False
    entry_value: Optional[float] = 0.0
    entry_via_alvara: Optional[bool] = False
    entry_date: Optional[str] = None
    created_at: Optional[str] = None

class AgreementUpdate(BaseModel):
    total_value: float
    installments_count: int
    installment_value: float
    first_due_date: str
    has_entry: bool
    entry_value: Optional[float] = None
    entry_via_alvara: bool
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

    cases = await db.cases.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)
    
    result = []
    for case in cases:
        result.append({
            **case,
            "total_received": case.get("total_received", 0.0),
            "percent_recovered": case.get("percent_recovered", 0.0),
            "status_acordo": case.get("status_acordo", "")
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
    agreement = await db.agreements.find_one({"id": agreement_id})
    if not agreement:
        raise HTTPException(status_code=404, detail="Agreement not found")

    case = await db.cases.find_one(
        {"id": agreement["case_id"], "user_id": current_user["id"]}
    )
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    # Atualiza o acordo
    await db.agreements.update_one(
        {"id": agreement_id},
        {
            "$set": {
                "total_value": payload.total_value,
                "installments_count": payload.installments_count,
                "installment_value": payload.installment_value,
                "first_due_date": payload.first_due_date,
                "has_entry": payload.has_entry,
                "entry_value": payload.entry_value,
                "entry_via_alvara": payload.entry_via_alvara,
                "entry_date": payload.entry_date,
            }
        }
    )

        # 2️⃣ Remove SOMENTE parcelas NÃO pagas
    await db.installments.delete_many({
        "agreement_id": agreement_id,
        "paid_date": None
    })

    # 3️⃣ Recria parcelas futuras
    from datetime import datetime
    from dateutil.relativedelta import relativedelta

    due_date = datetime.fromisoformat(data.first_due_date)

    for i in range(1, data.installments_count + 1):
        installment = {
            "id": str(uuid.uuid4()),
            "agreement_id": agreement_id,
            "number": i,
            "due_date": due_date.date().isoformat(),
            "value": data.installment_value,
            "paid_date": None,
            "paid_value": None,
            "created_at": datetime.utcnow().isoformat(),
        }
        await db.installments.insert_one(installment)
        due_date += relativedelta(months=1)

    await update_case_materialized_fields(agreement["case_id"])

    return {"message": "Agreement updated successfully"}
 
    # Buscar parcelas
    installments = await db.installments.find(
        {"agreement_id": agreement_id}
    ).to_list(None)

    # Filtrar parcelas NÃO pagas
    unpaid_installments = [
        inst for inst in installments
        if inst.get("status_calc") != "Pago"
    ]

    # Recalcular vencimentos apenas das parcelas não pagas
    due_date = datetime.fromisoformat(payload.first_due_date)

    for inst in unpaid_installments:
        await db.installments.update_one(
            {"id": inst["id"]},
            {
                "$set": {
                    "due_date": due_date.date().isoformat(),
                    "value": payload.installment_value
                }
            }
        )
        due_date = due_date.replace(month=due_date.month + 1)

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


app.include_router(api_router)
