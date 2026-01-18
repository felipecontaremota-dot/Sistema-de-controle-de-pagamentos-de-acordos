import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timedelta, timezone
import os
from dotenv import load_dotenv
from pathlib import Path
import uuid
from passlib.context import CryptContext

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def extract_beneficiary_code(text: str):
    if "31" in text:
        return "31"
    elif "14" in text:
        return "14"
    return None


async def clear_collections():
    await db.users.delete_many({})
    await db.cases.delete_many({})
    await db.agreements.delete_many({})
    await db.installments.delete_many({})
    print("Coleções limpas!")


async def create_seed_data():
    user_id = str(uuid.uuid4())
    user = {
        "id": user_id,
        "email": "advogado@teste.com",
        "password": hash_password("senha123"),
        "full_name": "Dr. João Silva",
        "role": "user",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.users.insert_one(user)
    print(f"Usuário criado: {user['email']} / senha: senha123")

    cases_data = [
        {
            "debtor_name": "Maria Santos",
            "internal_id": "PROC-2024-001",
            "value_causa": 50000.00,
            "has_agreement": True,
            "polo_ativo_text": "Banco 31 - Conta Principal",
            "notes": "Acordo firmado em audiência",
        },
        {
            "debtor_name": "Pedro Oliveira",
            "internal_id": "PROC-2024-002",
            "value_causa": 75000.00,
            "has_agreement": True,
            "polo_ativo_text": "Escritório 14 - Advocacia Associada",
            "notes": "Cliente possui imóvel para garantia",
        },
        {
            "debtor_name": "Ana Costa",
            "internal_id": "PROC-2024-003",
            "value_causa": 30000.00,
            "has_agreement": True,
            "polo_ativo_text": "Banco 31 - Filial Centro",
            "notes": "Acordo em andamento",
        },
        {
            "debtor_name": "Carlos Mendes",
            "internal_id": "PROC-2024-004",
            "value_causa": 100000.00,
            "has_agreement": False,
            "polo_ativo_text": "Empresa 14 - Cobrança Judicial",
            "notes": "Aguardando citação",
        },
        {
            "debtor_name": "Juliana Lima",
            "internal_id": "PROC-2024-005",
            "value_causa": 25000.00,
            "has_agreement": True,
            "polo_ativo_text": "Banco 31 - Agência 1234",
            "notes": "Acordo com desconto",
        },
    ]

    for case_data in cases_data:
        case_id = str(uuid.uuid4())
        case = {
            "id": case_id,
            **case_data,
            "polo_ativo_codigo": extract_beneficiary_code(case_data["polo_ativo_text"]),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "user_id": user_id,
        }
        await db.cases.insert_one(case)
        print(f"Caso criado: {case['debtor_name']}")

        if case["has_agreement"]:
            installments_count = 12 if case["value_causa"] > 50000 else 6
            installment_value = case["value_causa"] / installments_count
            
            agreement_id = str(uuid.uuid4())
            first_due = datetime(2024, 11, 15)
            
            agreement = {
                "id": agreement_id,
                "case_id": case_id,
                "total_value": case["value_causa"],
                "installments_count": installments_count,
                "installment_value": installment_value,
                "first_due_date": first_due.strftime("%Y-%m-%d"),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.agreements.insert_one(agreement)
            print(f"  Acordo criado: {installments_count} parcelas de R$ {installment_value:.2f}")

            for i in range(installments_count):
                due_date = first_due + timedelta(days=30 * i)
                installment_id = str(uuid.uuid4())
                
                paid_date = None
                paid_value = None
                
                if i < 2:
                    paid_date = (due_date - timedelta(days=2)).strftime("%Y-%m-%d")
                    paid_value = installment_value
                elif i == 2:
                    pass
                
                installment = {
                    "id": installment_id,
                    "agreement_id": agreement_id,
                    "number": i + 1,
                    "due_date": due_date.strftime("%Y-%m-%d"),
                    "paid_date": paid_date,
                    "paid_value": paid_value,
                    "status_calc": "Pago" if paid_date else "pending",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                await db.installments.insert_one(installment)

    print("\nDados de seed criados com sucesso!")
    print("\nPara fazer login, use:")
    print("  Email: advogado@teste.com")
    print("  Senha: senha123")


async def main():
    await clear_collections()
    await create_seed_data()
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
