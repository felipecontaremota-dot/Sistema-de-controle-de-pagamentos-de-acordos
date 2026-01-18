import requests
import sys
import json
from datetime import datetime, timedelta

class JudicialAgreementTester:
    def __init__(self, base_url="https://legacord.preview.emergentagent.com"):
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []
        self.created_case_id = None
        self.created_agreement_id = None
        self.created_installment_id = None
        self.created_alvara_id = None

    def log_test(self, name, success, details=""):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {name} - PASSED")
        else:
            print(f"❌ {name} - FAILED: {details}")
        
        self.test_results.append({
            "test": name,
            "success": success,
            "details": details
        })

    def run_test(self, name, method, endpoint, expected_status, data=None, headers=None):
        """Run a single API test"""
        url = f"{self.api_url}/{endpoint}"
        test_headers = {'Content-Type': 'application/json'}
        
        if self.token:
            test_headers['Authorization'] = f'Bearer {self.token}'
        
        if headers:
            test_headers.update(headers)

        print(f"\n🔍 Testing {name}...")
        print(f"   URL: {url}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=test_headers)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=test_headers)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=test_headers)
            elif method == 'DELETE':
                response = requests.delete(url, headers=test_headers)

            success = response.status_code == expected_status
            
            if success:
                self.log_test(name, True)
                try:
                    return True, response.json()
                except:
                    return True, {}
            else:
                error_msg = f"Expected {expected_status}, got {response.status_code}"
                try:
                    error_detail = response.json()
                    error_msg += f" - {error_detail}"
                except:
                    error_msg += f" - {response.text}"
                self.log_test(name, False, error_msg)
                return False, {}

        except Exception as e:
            self.log_test(name, False, f"Exception: {str(e)}")
            return False, {}

    def test_auth_login(self):
        """Test login with provided credentials"""
        success, response = self.run_test(
            "Login with test credentials",
            "POST",
            "auth/login",
            200,
            data={"email": "advogado@teste.com", "password": "senha123"}
        )
        if success and 'token' in response:
            self.token = response['token']
            print(f"   Token obtained: {self.token[:20]}...")
            return True
        return False

    def test_auth_me(self):
        """Test get current user"""
        success, response = self.run_test(
            "Get current user",
            "GET",
            "auth/me",
            200
        )
        return success

    def test_create_case(self):
        """Test creating a new case with FASE 2 fields"""
        case_data = {
            "debtor_name": "João Silva Teste",
            "internal_id": "CASE-TEST-001",
            "value_causa": 50000.00,
            "polo_ativo_text": "Banco 31 - Conta principal",
            "notes": "Caso de teste para automação",
            "numero_processo": "1234567-89.2024.8.26.0001",
            "data_protocolo": "2024-01-15",
            "status_processo": "Execução",
            "data_matricula": "2024-01-10",
            "cpf": "123.456.789-00",
            "curso": "Direito"
        }
        
        success, response = self.run_test(
            "Create new case",
            "POST",
            "cases",
            200,
            data=case_data
        )
        
        if success and 'id' in response:
            self.created_case_id = response['id']
            print(f"   Created case ID: {self.created_case_id}")
            
            # Verify beneficiary extraction
            if response.get('polo_ativo_codigo') == '31':
                self.log_test("Beneficiary extraction (31)", True)
            else:
                self.log_test("Beneficiary extraction (31)", False, f"Expected '31', got '{response.get('polo_ativo_codigo')}'")
            
            # Verify new FASE 2 fields
            fase2_fields = ['numero_processo', 'data_protocolo', 'status_processo', 'data_matricula', 'cpf', 'curso']
            for field in fase2_fields:
                if field in response and response[field] == case_data[field]:
                    self.log_test(f"FASE 2 field - {field}", True)
                else:
                    self.log_test(f"FASE 2 field - {field}", False, f"Expected '{case_data[field]}', got '{response.get(field)}'")
        
        return success

    def test_get_cases(self):
        """Test listing cases with filters"""
        # Test basic listing
        success, response = self.run_test(
            "List all cases",
            "GET",
            "cases",
            200
        )
        
        if not success:
            return False
        
        # Test search filter
        success, response = self.run_test(
            "Search cases by debtor name",
            "GET",
            "cases?search=João",
            200
        )
        
        if not success:
            return False
        
        # Test beneficiary filter
        success, response = self.run_test(
            "Filter cases by beneficiary",
            "GET",
            "cases?beneficiario=31",
            200
        )
        
        if not success:
            return False
        
        # Test status_processo filter
        success, response = self.run_test(
            "Filter cases by status_processo",
            "GET",
            "cases?status_processo=Execução",
            200
        )
        
        return success

    def test_get_case_detail(self):
        """Test getting case details"""
        if not self.created_case_id:
            self.log_test("Get case detail", False, "No case ID available")
            return False
        
        success, response = self.run_test(
            "Get case detail",
            "GET",
            f"cases/{self.created_case_id}",
            200
        )
        
        if success:
            # Verify response structure
            required_fields = ['case', 'agreement', 'installments', 'total_received', 'percent_recovered']
            for field in required_fields:
                if field not in response:
                    self.log_test(f"Case detail structure - {field}", False, f"Missing field: {field}")
                else:
                    self.log_test(f"Case detail structure - {field}", True)
        
        return success

    def test_create_agreement_with_entry(self):
        """Test creating an agreement with entrada"""
        if not self.created_case_id:
            self.log_test("Create agreement with entry", False, "No case ID available")
            return False
        
        # Calculate dates
        entry_date = datetime.now().strftime("%Y-%m-%d")
        first_due = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        
        agreement_data = {
            "case_id": self.created_case_id,
            "total_value": 30000.00,
            "installments_count": 12,
            "installment_value": 2291.67,  # (30000 - 2500) / 12
            "first_due_date": first_due,
            "has_entry": True,
            "entry_value": 2500.00,
            "entry_via_alvara": False,
            "entry_date": entry_date
        }
        
        success, response = self.run_test(
            "Create agreement with entry",
            "POST",
            "agreements",
            200,
            data=agreement_data
        )
        
        if success and 'id' in response:
            self.created_agreement_id = response['id']
            print(f"   Created agreement ID: {self.created_agreement_id}")
            
            # Verify entry fields
            if response.get('has_entry') == True:
                self.log_test("Agreement has_entry field", True)
            else:
                self.log_test("Agreement has_entry field", False)
                
            if response.get('entry_value') == 2500.00:
                self.log_test("Agreement entry_value field", True)
            else:
                self.log_test("Agreement entry_value field", False)
        
        return success

    def test_create_agreement_with_entry_via_alvara(self):
        """Test creating agreement with entry via alvará"""
        # First delete the existing agreement to test alvará entry
        if self.created_agreement_id:
            # We need to create a new case for this test
            case_data = {
                "debtor_name": "Maria Santos Teste Alvará",
                "internal_id": "CASE-ALVARA-001",
                "value_causa": 40000.00,
                "polo_ativo_text": "Banco 14 - Conta secundária",
                "notes": "Caso de teste para entrada via alvará"
            }
            
            success, response = self.run_test(
                "Create case for alvará entry test",
                "POST",
                "cases",
                200,
                data=case_data
            )
            
            if not success:
                return False
                
            case_id_alvara = response['id']
            
            # Create agreement with entry via alvará
            entry_date = datetime.now().strftime("%Y-%m-%d")
            first_due = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
            
            agreement_data = {
                "case_id": case_id_alvara,
                "total_value": 25000.00,
                "installments_count": 10,
                "installment_value": 2250.00,  # (25000 - 2500) / 10
                "first_due_date": first_due,
                "has_entry": True,
                "entry_value": 2500.00,
                "entry_via_alvara": True,
                "entry_date": entry_date
            }
            
            success, response = self.run_test(
                "Create agreement with entry via alvará",
                "POST",
                "agreements",
                200,
                data=agreement_data
            )
            
            if success:
                # Check if alvará was automatically created
                success_alvara, alvaras_response = self.run_test(
                    "Check automatic alvará creation",
                    "GET",
                    f"alvaras?case_id={case_id_alvara}",
                    200
                )
                
                if success_alvara and len(alvaras_response) > 0:
                    self.log_test("Automatic alvará creation", True)
                    self.created_alvara_id = alvaras_response[0]['id']
                else:
                    self.log_test("Automatic alvará creation", False, "No alvará found")
            
            # Cleanup this test case
            self.run_test(
                "Cleanup alvará test case",
                "DELETE",
                f"cases/{case_id_alvara}",
                200
            )
            
            return success
        
        return True

    def test_installments_generation(self):
        """Test that installments were automatically generated"""
        if not self.created_case_id:
            self.log_test("Check installments generation", False, "No case ID available")
            return False
        
        success, response = self.run_test(
            "Check installments generation",
            "GET",
            f"cases/{self.created_case_id}",
            200
        )
        
        if success:
            installments = response.get('installments', [])
            if len(installments) == 12:
                self.log_test("Installments count", True)
                
                # Check installment status calculation
                for inst in installments:
                    if 'status_calc' in inst:
                        self.log_test(f"Installment #{inst['number']} status calculation", True)
                    else:
                        self.log_test(f"Installment #{inst['number']} status calculation", False, "Missing status_calc")
                
                # Store first installment ID for payment test
                if installments:
                    self.created_installment_id = installments[0]['id']
                    print(f"   First installment ID: {self.created_installment_id}")
                
            else:
                self.log_test("Installments count", False, f"Expected 12, got {len(installments)}")
        
        return success

    def test_mark_installment_paid(self):
        """Test marking an installment as paid"""
        if not self.created_installment_id:
            self.log_test("Mark installment as paid", False, "No installment ID available")
            return False
        
        payment_data = {
            "paid_date": datetime.now().strftime("%Y-%m-%d"),
            "paid_value": 2500.00
        }
        
        success, response = self.run_test(
            "Mark installment as paid",
            "PUT",
            f"installments/{self.created_installment_id}",
            200,
            data=payment_data
        )
        
        if success:
            # Verify status changed to "Pago"
            if response.get('status_calc') == 'Pago':
                self.log_test("Installment status update to 'Pago'", True)
            else:
                self.log_test("Installment status update to 'Pago'", False, f"Expected 'Pago', got '{response.get('status_calc')}'")
        
        return success

    def test_recovery_percentage_calculation(self):
        """Test recovery percentage calculation"""
        if not self.created_case_id:
            self.log_test("Recovery percentage calculation", False, "No case ID available")
            return False
        
        success, response = self.run_test(
            "Check recovery percentage",
            "GET",
            f"cases/{self.created_case_id}",
            200
        )
        
        if success:
            percent_recovered = response.get('percent_recovered', 0)
            total_received = response.get('total_received', 0)
            
            # Should include: paid installment (2291.67) + entry (2500) + alvará (5500) = 10291.67
            # Percentage: 10291.67 / 50000 * 100 = ~20.6%
            expected_percent = 20.6
            if abs(percent_recovered - expected_percent) < 1.0:  # Allow 1% tolerance
                self.log_test("Recovery percentage calculation", True, f"Percent: {percent_recovered}%, Total: {total_received}")
            else:
                self.log_test("Recovery percentage calculation", False, f"Expected ~{expected_percent}%, got {percent_recovered}%")
        
        return success

    def test_alvara_crud_operations(self):
        """Test Alvará CRUD operations"""
        if not self.created_case_id:
            self.log_test("Alvará CRUD operations", False, "No case ID available")
            return False
        
        # Create alvará
        alvara_data = {
            "case_id": self.created_case_id,
            "data_alvara": datetime.now().strftime("%Y-%m-%d"),
            "valor_alvara": 5000.00,
            "beneficiario_codigo": "31",
            "observacoes": "Alvará de teste"
        }
        
        success, response = self.run_test(
            "Create alvará",
            "POST",
            "alvaras",
            200,
            data=alvara_data
        )
        
        if not success:
            return False
            
        alvara_id = response['id']
        self.created_alvara_id = alvara_id
        
        # Read alvará
        success, response = self.run_test(
            "Get alvarás for case",
            "GET",
            f"alvaras?case_id={self.created_case_id}",
            200
        )
        
        if not success:
            return False
        
        # Update alvará
        update_data = {
            "valor_alvara": 5500.00,
            "observacoes": "Alvará de teste atualizado"
        }
        
        success, response = self.run_test(
            "Update alvará",
            "PUT",
            f"alvaras/{alvara_id}",
            200,
            data=update_data
        )
        
        if success and response.get('valor_alvara') == 5500.00:
            self.log_test("Alvará update verification", True)
        else:
            self.log_test("Alvará update verification", False)
        
        # Delete alvará will be done in cleanup
        return success

    def test_receipts_endpoint(self):
        """Test receipts endpoint with filters"""
        # Test basic receipts
        success, response = self.run_test(
            "Get receipts - all",
            "GET",
            "receipts",
            200
        )
        
        if not success:
            return False
        
        # Verify response structure
        required_fields = ['receipts', 'kpis', 'monthly_consolidation']
        for field in required_fields:
            if field in response:
                self.log_test(f"Receipts response - {field}", True)
            else:
                self.log_test(f"Receipts response - {field}", False, f"Missing field: {field}")
        
        # Test with preset filter
        success, response = self.run_test(
            "Get receipts - month preset",
            "GET",
            "receipts?preset=month",
            200
        )
        
        if not success:
            return False
        
        # Test with beneficiary filter
        success, response = self.run_test(
            "Get receipts - beneficiary filter",
            "GET",
            "receipts?beneficiario=31",
            200
        )
        
        if not success:
            return False
        
        # Test with type filter
        success, response = self.run_test(
            "Get receipts - type filter",
            "GET",
            "receipts?type=parcelas",
            200
        )
        
        return success

    def test_total_received_calculation(self):
        """Test total_received calculation including alvarás"""
        if not self.created_case_id:
            self.log_test("Total received calculation", False, "No case ID available")
            return False
        
        success, response = self.run_test(
            "Check total received with alvará",
            "GET",
            f"cases/{self.created_case_id}",
            200
        )
        
        if success:
            total_received = response.get('total_received', 0)
            # Should include: paid installment (2500) + entry (2500) + alvará (5500) = 10500
            expected_total = 10500.00
            
            if abs(total_received - expected_total) < 0.1:
                self.log_test("Total received calculation with alvará", True, f"Total: {total_received}")
            else:
                self.log_test("Total received calculation with alvará", False, f"Expected ~{expected_total}, got {total_received}")
        
        return success

    def cleanup_test_data(self):
        """Clean up test data"""
        # Delete alvará first
        if self.created_alvara_id:
            success, _ = self.run_test(
                "Cleanup - Delete test alvará",
                "DELETE",
                f"alvaras/{self.created_alvara_id}",
                200
            )
        
        # Delete case (this will cascade delete agreement and installments)
        if self.created_case_id:
            success, _ = self.run_test(
                "Cleanup - Delete test case",
                "DELETE",
                f"cases/{self.created_case_id}",
                200
            )
            return success
        return True

    def run_all_tests(self):
        """Run all tests in sequence"""
        print("🚀 Starting Judicial Agreement System API Tests - FASE 2")
        print(f"   Base URL: {self.base_url}")
        print("=" * 60)
        
        # Authentication tests
        if not self.test_auth_login():
            print("❌ Authentication failed - stopping tests")
            return False
        
        self.test_auth_me()
        
        # Case management tests (FASE 2)
        self.test_create_case()
        self.test_get_cases()
        self.test_get_case_detail()
        
        # Agreement tests (FASE 2 - with entrada)
        self.test_create_agreement_with_entry()
        self.test_create_agreement_with_entry_via_alvara()
        self.test_installments_generation()
        self.test_mark_installment_paid()
        
        # Alvará tests (FASE 2)
        self.test_alvara_crud_operations()
        
        # Receipts and calculation tests (FASE 2)
        self.test_receipts_endpoint()
        self.test_total_received_calculation()
        self.test_recovery_percentage_calculation()
        
        # Cleanup
        self.cleanup_test_data()
        
        # Print summary
        print("\n" + "=" * 60)
        print(f"📊 Test Summary: {self.tests_passed}/{self.tests_run} tests passed")
        
        if self.tests_passed == self.tests_run:
            print("🎉 All FASE 2 tests passed!")
            return True
        else:
            print("⚠️  Some tests failed. Check details above.")
            return False

def main():
    tester = JudicialAgreementTester()
    success = tester.run_all_tests()
    
    # Save detailed results
    with open('/app/test_reports/backend_test_results.json', 'w') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'total_tests': tester.tests_run,
            'passed_tests': tester.tests_passed,
            'success_rate': (tester.tests_passed / tester.tests_run * 100) if tester.tests_run > 0 else 0,
            'test_results': tester.test_results
        }, f, indent=2)
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())