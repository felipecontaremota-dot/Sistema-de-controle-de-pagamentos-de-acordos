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
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone, timedelta
from passlib.context import CryptContext
from jose import JWTError, jwt
import re
import pandas as pd
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

IMPORT_UPLOAD_DIR = ROOT_DIR / "import_uploads"
IMPORT_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_IMPORT_EXTENSIONS = {".csv", ".xlsx", ".xls"}
ALLOWED_ALVARA_STATUS = {"Aguardando alvará", "Alvará pago"}
MAX_IMPORT_FILE_SIZE = 10 * 1024 * 1024


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


class ImportSession(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    filename: str
    file_path: str
    status: str = "uploaded"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ImportMapping(BaseModel):
    case: Dict[str, Optional[str]] = Field(default_factory=dict)
    agreement: Dict[str, Optional[str]] = Field(default_factory=dict)
    installment: Dict[str, Optional[str]] = Field(default_factory=dict)
    alvara: Dict[str, Optional[str]] = Field(default_factory=dict)


class ImportPreviewRequest(BaseModel):
    session_id: str
    sample_size: int = 10


class ImportValidateRequest(BaseModel):
    session_id: str
    mapping: ImportMapping


class ImportCommitRequest(BaseModel):
    session_id: str
    mapping: ImportMapping


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


def sanitize_filename(filename: str) -> str:
    return os.path.basename(filename).replace("..", "").strip()


def parse_bool(value: Any) -> Optional[bool]:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text == "":
        return None
    if text in {"true", "1", "sim", "yes", "y", "t"}:
        return True
    if text in {"false", "0", "nao", "não", "no", "n", "f"}:
        return False
    return None


def parse_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    text = text.replace("R$", "").replace(" ", "")
    if text.count(",") == 1 and text.count(".") >= 1:
        text = text.replace(".", "").replace(",", ".")
    elif text.count(",") == 1 and text.count(".") == 0:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def parse_int(value: Any) -> Optional[int]:
    parsed = parse_float(value)
    if parsed is None:
        return None
    if parsed.is_integer():
        return int(parsed)
    return None


def parse_date(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def load_import_dataframe(file_path: str, filename: str) -> pd.DataFrame:
    ext = Path(filename).suffix.lower()
    if ext in {".xls", ".xlsx"}:
        df = pd.read_excel(file_path, dtype=str)
    else:
        df = pd.read_csv(file_path, dtype=str)
    return df.fillna("")


def get_mapped_value(row: pd.Series, column_name: Optional[str]) -> Optional[str]:
    if not column_name:
        return None
    value = row.get(column_name)
    if value is None:
        return None
    text = str(value).strip()
    return text if text != "" else None


def build_case_key(case_data: Dict[str, Any]) -> Optional[str]:
    for key in ("internal_id", "numero_processo", "cpf", "debtor_name"):
        value = case_data.get(key)
        if value:
            return str(value).strip()
    return None


def has_section_data(row: pd.Series, mapping: Dict[str, Optional[str]]) -> bool:
    for column_name in mapping.values():
        if column_name and get_mapped_value(row, column_name):
            return True
    return False


def generate_installments_for_agreement(agreement_id: str, agreement_data: AgreementCreate) -> List[Installment]:
    installments: List[Installment] = []

    if agreement_data.has_entry and agreement_data.entry_date:
        entry_date = datetime.strptime(agreement_data.entry_date, "%Y-%m-%d")
        if entry_date.month == 12:
            first_due = entry_date.replace(year=entry_date.year + 1, month=1)
        else:
            first_due = entry_date.replace(month=entry_date.month + 1)
    else:
        first_due = datetime.strptime(agreement_data.first_due_date, "%Y-%m-%d")

    for i in range(agreement_data.installments_count):
        year = first_due.year
        month = first_due.month + i
        day = first_due.day

        while month > 12:
            month -= 12
            year += 1

        try:
            due_date = datetime(year, month, day)
        except ValueError:
            if month == 12:
                next_month = datetime(year + 1, 1, 1)
            else:
                next_month = datetime(year, month + 1, 1)
            due_date = next_month - timedelta(days=1)

        installments.append(
            Installment(
                agreement_id=agreement_id,
                number=i + 1,
                due_date=due_date.strftime("%Y-%m-%d"),
                is_entry=False
            )
        )

    return installments


def build_entry_installment(agreement_id: str, agreement_data: AgreementCreate) -> Optional[Installment]:
    if agreement_data.has_entry and not agreement_data.entry_via_alvara:
        return Installment(
            agreement_id=agreement_id,
            number=0,
            due_date=agreement_data.entry_date or agreement_data.first_due_date,
            paid_date=None,
            paid_value=None,
            is_entry=True
        )
    return None


def build_entry_alvara(agreement_data: AgreementCreate, case: Dict[str, Any]) -> Optional[Alvara]:
    if agreement_data.has_entry and agreement_data.entry_via_alvara and agreement_data.entry_value:
        return Alvara(
            case_id=agreement_data.case_id,
            data_alvara=agreement_data.entry_date,
            valor_alvara=agreement_data.entry_value,
            beneficiario_codigo=case.get("polo_ativo_codigo", "31"),
            observacoes="Entrada via Alvará Judicial",
            status_alvara="Aguardando alvará"
        )
    return None


def validate_import_data(
    df: pd.DataFrame,
    mapping: ImportMapping
) -> Dict[str, Any]:
    errors: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    row_case_keys: Dict[int, str] = {}
    prepared_cases: Dict[str, Dict[str, Any]] = {}
    prepared_agreements: Dict[str, Dict[str, Any]] = {}
    prepared_installments: Dict[str, List[Dict[str, Any]]] = {}
    prepared_alvaras: Dict[str, List[Dict[str, Any]]] = {}

    required_case_fields = {"debtor_name", "value_causa", "polo_ativo_text"}
    required_agreement_fields = {"total_value", "installments_count", "installment_value", "first_due_date"}
    required_installment_fields = {"number", "due_date"}
    required_alvara_fields = {"valor_alvara", "beneficiario_codigo", "status_alvara"}

    for idx, row in df.iterrows():
        row_number = idx + 2
        case_data = {
            "debtor_name": get_mapped_value(row, mapping.case.get("debtor_name")),
            "internal_id": get_mapped_value(row, mapping.case.get("internal_id")),
            "value_causa": get_mapped_value(row, mapping.case.get("value_causa")),
            "polo_ativo_text": get_mapped_value(row, mapping.case.get("polo_ativo_text")),
            "notes": get_mapped_value(row, mapping.case.get("notes")),
            "numero_processo": get_mapped_value(row, mapping.case.get("numero_processo")),
            "data_protocolo": get_mapped_value(row, mapping.case.get("data_protocolo")),
            "status_processo": get_mapped_value(row, mapping.case.get("status_processo")),
            "data_matricula": get_mapped_value(row, mapping.case.get("data_matricula")),
            "cpf": get_mapped_value(row, mapping.case.get("cpf")),
            "curso": get_mapped_value(row, mapping.case.get("curso")),
        }

        missing_case_fields = [field for field in required_case_fields if not case_data.get(field)]
        if missing_case_fields:
            errors.append({
                "row": row_number,
                "field": "case",
                "message": f"Campos obrigatórios do caso ausentes: {', '.join(missing_case_fields)}"
            })
            continue

        case_data["value_causa"] = parse_float(case_data["value_causa"])
        if case_data["value_causa"] is None:
            errors.append({
                "row": row_number,
                "field": "case.value_causa",
                "message": "Valor da causa inválido"
            })
            continue

        case_data["data_protocolo"] = parse_date(case_data.get("data_protocolo"))
        case_data["data_matricula"] = parse_date(case_data.get("data_matricula"))

        if extract_beneficiary_code(case_data.get("polo_ativo_text", "")) is None:
            warnings.append({
                "row": row_number,
                "field": "case.polo_ativo_text",
                "message": "Não foi possível identificar o beneficiário pelo polo ativo"
            })

        case_key = build_case_key(case_data)
        if not case_key:
            errors.append({
                "row": row_number,
                "field": "case",
                "message": "Não foi possível definir uma chave do caso (use ID interno, nº processo, CPF ou nome)"
            })
            continue

        if case_key in prepared_cases:
            for field, value in case_data.items():
                existing = prepared_cases[case_key].get(field)
                if value and existing and value != existing:
                    errors.append({
                        "row": row_number,
                        "field": f"case.{field}",
                        "message": "Dados conflitantes para o mesmo caso"
                    })
        else:
            prepared_cases[case_key] = case_data
        row_case_keys[row_number] = case_key

        if has_section_data(row, mapping.agreement):
            agreement_data = {
                "total_value": parse_float(get_mapped_value(row, mapping.agreement.get("total_value"))),
                "installments_count": parse_int(get_mapped_value(row, mapping.agreement.get("installments_count"))),
                "installment_value": parse_float(get_mapped_value(row, mapping.agreement.get("installment_value"))),
                "first_due_date": parse_date(get_mapped_value(row, mapping.agreement.get("first_due_date"))),
                "has_entry": parse_bool(get_mapped_value(row, mapping.agreement.get("has_entry"))) or False,
                "entry_value": parse_float(get_mapped_value(row, mapping.agreement.get("entry_value"))),
                "entry_via_alvara": parse_bool(get_mapped_value(row, mapping.agreement.get("entry_via_alvara"))) or False,
                "entry_date": parse_date(get_mapped_value(row, mapping.agreement.get("entry_date"))),
            }

            missing_agreement = [
                field for field in required_agreement_fields
                if agreement_data.get(field) in (None, "")
            ]
            if missing_agreement:
                errors.append({
                    "row": row_number,
                    "field": "agreement",
                    "message": f"Campos obrigatórios do acordo ausentes: {', '.join(missing_agreement)}"
                })
            else:
                if agreement_data["installments_count"] <= 0:
                    errors.append({
                        "row": row_number,
                        "field": "agreement.installments_count",
                        "message": "Quantidade de parcelas inválida"
                    })
                if agreement_data["total_value"] <= 0 or agreement_data["installment_value"] <= 0:
                    errors.append({
                        "row": row_number,
                        "field": "agreement",
                        "message": "Valores do acordo devem ser maiores que zero"
                    })

            if case_key in prepared_agreements:
                existing = prepared_agreements[case_key]
                for field, value in agreement_data.items():
                    existing_value = existing.get(field)
                    if value is not None and existing_value is not None and value != existing_value:
                        errors.append({
                            "row": row_number,
                            "field": f"agreement.{field}",
                            "message": "Dados conflitantes para o acordo do mesmo caso"
                        })
            else:
                prepared_agreements[case_key] = agreement_data

        if has_section_data(row, mapping.installment):
            if case_key not in prepared_agreements:
                errors.append({
                    "row": row_number,
                    "field": "installment",
                    "message": "Parcela informada sem acordo associado"
                })
            installment_data = {
                "number": parse_int(get_mapped_value(row, mapping.installment.get("number"))),
                "due_date": parse_date(get_mapped_value(row, mapping.installment.get("due_date"))),
                "paid_date": parse_date(get_mapped_value(row, mapping.installment.get("paid_date"))),
                "paid_value": parse_float(get_mapped_value(row, mapping.installment.get("paid_value"))),
                "is_entry": parse_bool(get_mapped_value(row, mapping.installment.get("is_entry"))) or False
            }

            missing_installment = [
                field for field in required_installment_fields
                if installment_data.get(field) in (None, "")
            ]
            if missing_installment:
                errors.append({
                    "row": row_number,
                    "field": "installment",
                    "message": f"Campos obrigatórios da parcela ausentes: {', '.join(missing_installment)}"
                })
            if installment_data["paid_date"] and installment_data["paid_value"] is None:
                errors.append({
                    "row": row_number,
                    "field": "installment.paid_value",
                    "message": "Parcela com data de pagamento sem valor pago"
                })
            if installment_data["paid_value"] is not None and not installment_data["paid_date"]:
                errors.append({
                    "row": row_number,
                    "field": "installment.paid_date",
                    "message": "Parcela com valor pago sem data de pagamento"
                })

            prepared_installments.setdefault(case_key, []).append(installment_data)

        if has_section_data(row, mapping.alvara):
            alvara_data = {
                "data_alvara": parse_date(get_mapped_value(row, mapping.alvara.get("data_alvara"))),
                "valor_alvara": parse_float(get_mapped_value(row, mapping.alvara.get("valor_alvara"))),
                "beneficiario_codigo": get_mapped_value(row, mapping.alvara.get("beneficiario_codigo")),
                "observacoes": get_mapped_value(row, mapping.alvara.get("observacoes")),
                "status_alvara": get_mapped_value(row, mapping.alvara.get("status_alvara")) or "Aguardando alvará"
            }

            missing_alvara = [
                field for field in required_alvara_fields
                if not alvara_data.get(field)
            ]
            if missing_alvara:
                errors.append({
                    "row": row_number,
                    "field": "alvara",
                    "message": f"Campos obrigatórios do alvará ausentes: {', '.join(missing_alvara)}"
                })
            if alvara_data["status_alvara"] not in ALLOWED_ALVARA_STATUS:
                errors.append({
                    "row": row_number,
                    "field": "alvara.status_alvara",
                    "message": "Status do alvará inválido"
                })
            if alvara_data["beneficiario_codigo"] not in {"31", "14"}:
                errors.append({
                    "row": row_number,
                    "field": "alvara.beneficiario_codigo",
                    "message": "Beneficiário do alvará inválido"
                })

            prepared_alvaras.setdefault(case_key, []).append(alvara_data)

    for case_key, agreement in prepared_agreements.items():
        installments = prepared_installments.get(case_key, [])
        if not installments:
            warnings.append({
                "row": None,
                "field": "installments",
                "message": f"Nenhuma parcela informada para o caso {case_key}; o sistema irá gerar parcelas padrão"
            })
        else:
            installment_numbers = {inst["number"] for inst in installments if inst.get("number") is not None}
            if len(installment_numbers) != len(installments):
                warnings.append({
                    "row": None,
                    "field": "installments.number",
                    "message": f"Há parcelas duplicadas para o caso {case_key}"
                })
            if agreement.get("installments_count") and len(installments) != agreement.get("installments_count"):
                warnings.append({
                    "row": None,
                    "field": "agreement.installments_count",
                    "message": f"Quantidade de parcelas diferente do acordo para o caso {case_key}"
                })

        expected_total = agreement.get("installment_value", 0) * agreement.get("installments_count", 0)
        if agreement.get("has_entry") and agreement.get("entry_value"):
            expected_total += agreement.get("entry_value")
        if agreement.get("total_value") is not None and expected_total:
            if abs(agreement["total_value"] - expected_total) > 0.01:
                warnings.append({
                    "row": None,
                    "field": "agreement.total_value",
                    "message": f"Soma das parcelas difere do total do acordo para o caso {case_key}"
                })

        if agreement.get("entry_via_alvara") and agreement.get("entry_value") and not prepared_alvaras.get(case_key):
            warnings.append({
                "row": None,
                "field": "alvara",
                "message": f"Entrada via alvará sem alvará informado para o caso {case_key}; será criado automaticamente"
            })

        if installments and agreement.get("installments_count") and len(installments) == agreement.get("installments_count"):
            if all(inst.get("paid_date") for inst in installments):
                has_pending_alvara = any(
                    alvara.get("status_alvara") == "Aguardando alvará"
                    for alvara in prepared_alvaras.get(case_key, [])
                )
                if has_pending_alvara:
                    warnings.append({
                        "row": None,
                        "field": "alvara.status_alvara",
                        "message": f"Acordo quitado com alvará pendente para o caso {case_key}"
                    })

    rows_with_errors = {error.get("row") for error in errors if error.get("row")}
    total_rows = len(df.index)
    valid_rows = total_rows - len(rows_with_errors)

    return {
        "errors": errors,
        "warnings": warnings,
        "row_case_keys": row_case_keys,
        "prepared": {
            "cases": prepared_cases,
            "agreements": prepared_agreements,
            "installments": prepared_installments,
            "alvaras": prepared_alvaras
        },
        "summary": {
            "total_rows": total_rows,
            "valid_rows": max(valid_rows, 0),
            "invalid_rows": len(rows_with_errors)
        }
    }


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
    entry_installment = build_entry_installment(agreement.id, agreement_data)
    if entry_installment:
        entry_doc = entry_installment.model_dump()
        entry_doc["created_at"] = entry_doc["created_at"].isoformat()
        await db.installments.insert_one(entry_doc)
    
    installments = generate_installments_for_agreement(agreement.id, agreement_data)
    for installment in installments:
        inst_doc = installment.model_dump()
        inst_doc["created_at"] = inst_doc["created_at"].isoformat()
        await db.installments.insert_one(inst_doc)
    
    # Se entrada via alvará, criar registro de alvará automaticamente
    entry_alvara = build_entry_alvara(agreement_data, case)
    if entry_alvara:
        alvara_doc = entry_alvara.model_dump()
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


@api_router.post("/import/upload")
async def upload_import_file(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    filename = sanitize_filename(file.filename or "")
    if not filename:
        raise HTTPException(status_code=400, detail="Nome de arquivo inválido")

    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_IMPORT_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Formato de arquivo não suportado")

    session = ImportSession(
        user_id=current_user["id"],
        filename=filename,
        file_path=str(IMPORT_UPLOAD_DIR / f"{uuid.uuid4()}{ext}")
    )

    contents = await file.read()
    if len(contents) > MAX_IMPORT_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Arquivo excede o tamanho máximo permitido")
    with open(session.file_path, "wb") as buffer:
        buffer.write(contents)

    doc = session.model_dump()
    doc["created_at"] = doc["created_at"].isoformat()
    await db.import_sessions.insert_one(doc)

    return {"session_id": session.id, "filename": filename}


@api_router.post("/import/preview")
async def preview_import_data(
    payload: ImportPreviewRequest,
    current_user: dict = Depends(get_current_user)
):
    session = await db.import_sessions.find_one(
        {"id": payload.session_id, "user_id": current_user["id"]},
        {"_id": 0}
    )
    if not session:
        raise HTTPException(status_code=404, detail="Sessão de importação não encontrada")

    df = load_import_dataframe(session["file_path"], session["filename"])
    preview_rows = df.head(payload.sample_size).to_dict(orient="records")

    return {
        "columns": df.columns.tolist(),
        "preview": preview_rows,
        "total_rows": len(df.index)
    }


@api_router.post("/import/validate")
async def validate_import(
    payload: ImportValidateRequest,
    current_user: dict = Depends(get_current_user)
):
    session = await db.import_sessions.find_one(
        {"id": payload.session_id, "user_id": current_user["id"]},
        {"_id": 0}
    )
    if not session:
        raise HTTPException(status_code=404, detail="Sessão de importação não encontrada")

    df = load_import_dataframe(session["file_path"], session["filename"])
    result = validate_import_data(df, payload.mapping)

    return {
        "summary": result["summary"],
        "errors": result["errors"],
        "warnings": result["warnings"]
    }


@api_router.post("/import/commit")
async def commit_import(
    payload: ImportCommitRequest,
    current_user: dict = Depends(get_current_user)
):
    session = await db.import_sessions.find_one(
        {"id": payload.session_id, "user_id": current_user["id"]},
        {"_id": 0}
    )
    if not session:
        raise HTTPException(status_code=404, detail="Sessão de importação não encontrada")

    df = load_import_dataframe(session["file_path"], session["filename"])
    result = validate_import_data(df, payload.mapping)
    if result["errors"]:
        raise HTTPException(status_code=400, detail={
            "message": "Importação contém erros bloqueantes",
            "errors": result["errors"]
        })

    prepared = result["prepared"]
    row_case_keys = result.get("row_case_keys", {})
    cases_data = prepared["cases"]
    agreements_data = prepared["agreements"]
    installments_data = prepared["installments"]
    alvaras_data = prepared["alvaras"]

    duplicate_errors = []
    for case_key, case_data in cases_data.items():
        numero_processo = case_data.get("numero_processo")
        internal_id = case_data.get("internal_id")
        query = {"user_id": current_user["id"]}
        if numero_processo:
            query["numero_processo"] = numero_processo
        elif internal_id:
            query["internal_id"] = internal_id
        else:
            continue
        existing = await db.cases.find_one(query, {"_id": 0})
        if existing:
            duplicate_errors.append({
                "case_key": case_key,
                "message": "Já existe um caso com o mesmo identificador"
            })

    if duplicate_errors:
        raise HTTPException(status_code=400, detail={
            "message": "Casos duplicados encontrados",
            "errors": duplicate_errors
        })

    inserted_case_ids = []
    inserted_agreement_ids = []
    inserted_installment_ids = []
    inserted_alvara_ids = []
    case_id_map: Dict[str, str] = {}
    agreement_id_map: Dict[str, str] = {}

    try:
        for case_key, case_data in cases_data.items():
            has_agreement = case_key in agreements_data
            status_processo = case_data.get("status_processo")
            if has_agreement:
                status_processo = "Acordo"

            case = Case(
                debtor_name=case_data["debtor_name"],
                internal_id=case_data.get("internal_id"),
                value_causa=case_data["value_causa"],
                has_agreement=has_agreement,
                polo_ativo_text=case_data["polo_ativo_text"],
                notes=case_data.get("notes"),
                numero_processo=case_data.get("numero_processo"),
                data_protocolo=case_data.get("data_protocolo"),
                status_processo=status_processo,
                data_matricula=case_data.get("data_matricula"),
                cpf=case_data.get("cpf"),
                curso=case_data.get("curso"),
                user_id=current_user["id"]
            )
            case.polo_ativo_codigo = extract_beneficiary_code(case.polo_ativo_text)
            case_doc = case.model_dump()
            case_doc["created_at"] = case_doc["created_at"].isoformat()
            await db.cases.insert_one(case_doc)
            inserted_case_ids.append(case.id)
            case_id_map[case_key] = case.id

        for case_key, agreement_data in agreements_data.items():
            agreement_payload = AgreementCreate(
                case_id=case_id_map[case_key],
                total_value=agreement_data["total_value"],
                installments_count=agreement_data["installments_count"],
                installment_value=agreement_data["installment_value"],
                first_due_date=agreement_data["first_due_date"],
                has_entry=agreement_data.get("has_entry", False),
                entry_value=agreement_data.get("entry_value"),
                entry_via_alvara=agreement_data.get("entry_via_alvara", False),
                entry_date=agreement_data.get("entry_date")
            )
            agreement = Agreement(**agreement_payload.model_dump())
            agreement_doc = agreement.model_dump()
            agreement_doc["created_at"] = agreement_doc["created_at"].isoformat()
            await db.agreements.insert_one(agreement_doc)
            inserted_agreement_ids.append(agreement.id)
            agreement_id_map[case_key] = agreement.id

            case_installments = installments_data.get(case_key, [])
            has_entry_installment = any(inst.get("is_entry") for inst in case_installments)
            entry_installment = build_entry_installment(agreement.id, agreement_payload)
            if entry_installment and not has_entry_installment:
                entry_doc = entry_installment.model_dump()
                entry_doc["created_at"] = entry_doc["created_at"].isoformat()
                entry_doc["status_calc"] = calculate_installment_status(
                    entry_doc["due_date"], entry_doc.get("paid_date")
                )
                await db.installments.insert_one(entry_doc)
                inserted_installment_ids.append(entry_installment.id)

            if not case_installments:
                installments = generate_installments_for_agreement(agreement.id, agreement_payload)
                for installment in installments:
                    inst_doc = installment.model_dump()
                    inst_doc["created_at"] = inst_doc["created_at"].isoformat()
                    inst_doc["status_calc"] = calculate_installment_status(
                        inst_doc["due_date"], inst_doc.get("paid_date")
                    )
                    await db.installments.insert_one(inst_doc)
                    inserted_installment_ids.append(installment.id)

            case_beneficiario = extract_beneficiary_code(
                cases_data[case_key].get("polo_ativo_text", "")
            ) or "31"
            entry_alvara = build_entry_alvara(agreement_payload, {"polo_ativo_codigo": case_beneficiario})
            if entry_alvara and not alvaras_data.get(case_key):
                alvara_doc = entry_alvara.model_dump()
                alvara_doc["created_at"] = alvara_doc["created_at"].isoformat()
                await db.alvaras.insert_one(alvara_doc)
                inserted_alvara_ids.append(entry_alvara.id)

        for case_key, installments in installments_data.items():
            agreement_id = agreement_id_map.get(case_key)
            if not agreement_id:
                continue
            for installment_data in installments:
                number = installment_data.get("number")
                if number is None and installment_data.get("is_entry"):
                    number = 0
                installment = Installment(
                    agreement_id=agreement_id,
                    number=number or 0,
                    due_date=installment_data["due_date"],
                    paid_date=installment_data.get("paid_date"),
                    paid_value=installment_data.get("paid_value"),
                    is_entry=installment_data.get("is_entry", False)
                )
                installment.status_calc = calculate_installment_status(
                    installment.due_date, installment.paid_date
                )
                inst_doc = installment.model_dump()
                inst_doc["created_at"] = inst_doc["created_at"].isoformat()
                await db.installments.insert_one(inst_doc)
                inserted_installment_ids.append(installment.id)

        for case_key, alvaras in alvaras_data.items():
            case_id = case_id_map.get(case_key)
            if not case_id:
                continue
            for alvara_data in alvaras:
                alvara = Alvara(
                    case_id=case_id,
                    data_alvara=alvara_data.get("data_alvara"),
                    valor_alvara=alvara_data["valor_alvara"],
                    beneficiario_codigo=alvara_data["beneficiario_codigo"],
                    observacoes=alvara_data.get("observacoes"),
                    status_alvara=alvara_data.get("status_alvara", "Aguardando alvará")
                )
                alvara_doc = alvara.model_dump()
                alvara_doc["created_at"] = alvara_doc["created_at"].isoformat()
                await db.alvaras.insert_one(alvara_doc)
                inserted_alvara_ids.append(alvara.id)

        import_log = {
            "id": str(uuid.uuid4()),
            "user_id": current_user["id"],
            "session_id": session["id"],
            "filename": session["filename"],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "totals": {
                "cases": len(inserted_case_ids),
                "agreements": len(inserted_agreement_ids),
                "installments": len(inserted_installment_ids),
                "alvaras": len(inserted_alvara_ids)
            },
            "warnings": len(result["warnings"])
        }
        await db.import_logs.insert_one(import_log)

        results = []
        for row_number in sorted(row_case_keys.keys()):
            results.append({
                "row": row_number,
                "case_key": row_case_keys[row_number],
                "status": "success",
                "message": "Linha importada com sucesso"
            })

        return {
            "message": "Importação concluída com sucesso",
            "totals": import_log["totals"],
            "results": results,
            "warnings": result["warnings"]
        }
    except Exception as exc:
        if inserted_installment_ids:
            await db.installments.delete_many({"id": {"$in": inserted_installment_ids}})
        if inserted_alvara_ids:
            await db.alvaras.delete_many({"id": {"$in": inserted_alvara_ids}})
        if inserted_agreement_ids:
            await db.agreements.delete_many({"id": {"$in": inserted_agreement_ids}})
        if inserted_case_ids:
            await db.cases.delete_many({"id": {"$in": inserted_case_ids}})
        raise HTTPException(
            status_code=500,
            detail="Falha na importação. Nenhum dado foi persistido."
        ) from exc


@api_router.get("/import/history")
async def get_import_history(current_user: dict = Depends(get_current_user)):
    logs = await db.import_logs.find(
        {"user_id": current_user["id"]},
        {"_id": 0}
    ).sort("created_at", -1).to_list(50)
    return logs


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
    await db.import_sessions.create_index("user_id")
    await db.import_sessions.create_index("created_at")
    await db.import_logs.create_index("user_id")
    await db.import_logs.create_index("created_at")


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
