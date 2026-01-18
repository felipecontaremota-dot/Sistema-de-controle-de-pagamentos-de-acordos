from fastapi import FastAPI, APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
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


class CaseUpdate(BaseModel):
    debtor_name: Optional[str] = None
    internal_id: Optional[str] = None
    value_causa: Optional[float] = None
    has_agreement: Optional[bool] = None
    polo_ativo_text: Optional[str] = None
    notes: Optional[str] = None


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
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    user_id: str


class AgreementCreate(BaseModel):
    case_id: str
    total_value: float
    installments_count: int
    installment_value: float
    first_due_date: str


class Agreement(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    case_id: str
    total_value: float
    installments_count: int
    installment_value: float
    first_due_date: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class InstallmentUpdate(BaseModel):
    paid_date: Optional[str] = None
    paid_value: Optional[float] = None


class Installment(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agreement_id: str
    number: int
    due_date: str
    paid_date: Optional[str] = None
    paid_value: Optional[float] = None
    status_calc: str = "pending"
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
    current_user: dict = Depends(get_current_user)
):
    query = {"user_id": current_user["id"]}
    
    if search:
        query["debtor_name"] = {"$regex": search, "$options": "i"}
    if has_agreement is not None:
        query["has_agreement"] = has_agreement
    if beneficiario:
        query["polo_ativo_codigo"] = beneficiario
    
    cases = await db.cases.find(query, {"_id": 0}).to_list(1000)
    
    result = []
    for case in cases:
        case_id = case["id"]
        
        total_received = 0.0
        installments = await db.installments.find({"paid_date": {"$ne": None}}, {"_id": 0}).to_list(1000)
        for inst in installments:
            agreement = await db.agreements.find_one({"id": inst["agreement_id"]}, {"_id": 0})
            if agreement and agreement["case_id"] == case_id:
                total_received += inst.get("paid_value", 0)
        
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
    
    total_received = sum(inst.get("paid_value", 0) for inst in installments if inst.get("paid_date"))
    percent_recovered = (total_received / case["value_causa"] * 100) if case["value_causa"] > 0 else 0
    
    return {
        "case": case,
        "agreement": agreement,
        "installments": installments,
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
    
    agreement = await db.agreements.find_one({"case_id": case_id}, {"_id": 0})
    if agreement:
        await db.installments.delete_many({"agreement_id": agreement["id"]})
        await db.agreements.delete_one({"id": agreement["id"]})
    
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
    
    first_due = datetime.strptime(agreement_data.first_due_date, "%Y-%m-%d")
    for i in range(agreement_data.installments_count):
        due_date = first_due + timedelta(days=30 * i)
        installment = Installment(
            agreement_id=agreement.id,
            number=i + 1,
            due_date=due_date.strftime("%Y-%m-%d")
        )
        inst_doc = installment.model_dump()
        inst_doc["created_at"] = inst_doc["created_at"].isoformat()
        await db.installments.insert_one(inst_doc)
    
    await db.cases.update_one({"id": agreement_data.case_id}, {"$set": {"has_agreement": True}})
    
    return agreement


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
    await db.agreements.create_index("case_id")
    await db.installments.create_index("agreement_id")
    await db.installments.create_index("due_date")


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()