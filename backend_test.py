import requests
import sys
import json
from datetime import datetime, date, timedelta

class ContractAPITester:
    def __init__(self, base_url="https://docusense-2.preview.emergentagent.com"):
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        self.tests_run = 0
        self.tests_passed = 0
        self.created_contract_id = None
        self.expired_contract_id = None

    def run_test(self, name, method, endpoint, expected_status, data=None, headers=None):
        """Run a single API test"""
        url = f"{self.api_url}/{endpoint}" if endpoint else f"{self.api_url}"
        if headers is None:
            headers = {'Content-Type': 'application/json'}

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        print(f"   URL: {url}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=30)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=30)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, timeout=30)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=30)

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    response_data = response.json()
                    print(f"   Response: {json.dumps(response_data, indent=2)[:200]}...")
                    return True, response_data
                except:
                    return True, {}
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                try:
                    error_data = response.json()
                    print(f"   Error: {error_data}")
                except:
                    print(f"   Error: {response.text}")
                return False, {}

        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            return False, {}

    def test_health_check(self):
        """Test API health check"""
        return self.run_test("Health Check", "GET", "", 200)

    def test_create_contract(self):
        """Test contract creation with email field"""
        contract_data = {
            "name": "Test Service Agreement",
            "client": "Test Client Corp",
            "contact_email": "test@example.com",
            "start_date": "2024-01-15",
            "expiry_date": "2025-01-15",
            "status": "Active"
        }
        
        success, response = self.run_test(
            "Create Contract with Email",
            "POST",
            "contracts",
            200,
            data=contract_data
        )
        
        if success and 'id' in response:
            self.created_contract_id = response['id']
            print(f"   Created contract ID: {self.created_contract_id}")
            # Verify email field is included
            if response.get('contact_email') == contract_data['contact_email']:
                print("   ✅ Email field correctly saved")
            else:
                print(f"   ⚠️  Email field issue: expected {contract_data['contact_email']}, got {response.get('contact_email')}")
        
        return success

    def test_create_expired_contract(self):
        """Test creating an expired contract for renewal testing"""
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        contract_data = {
            "name": "Expired Test Contract",
            "client": "Expired Client Corp",
            "contact_email": "expired@example.com",
            "start_date": "2023-01-15",
            "expiry_date": yesterday,
            "status": "Active"  # Will be auto-updated to Expired
        }
        
        success, response = self.run_test(
            "Create Expired Contract",
            "POST",
            "contracts",
            200,
            data=contract_data
        )
        
        if success and 'id' in response:
            self.expired_contract_id = response['id']
            print(f"   Created expired contract ID: {self.expired_contract_id}")
        
        return success

    def test_get_contracts(self):
        """Test getting all contracts and verify status auto-update"""
        success, response = self.run_test("Get All Contracts", "GET", "contracts", 200)
        
        if success and isinstance(response, list):
            print(f"   Found {len(response)} contracts")
            
            # Check if expired contract status was auto-updated
            if self.expired_contract_id:
                expired_contract = next((c for c in response if c['id'] == self.expired_contract_id), None)
                if expired_contract:
                    if expired_contract['status'] == 'Expired':
                        print("   ✅ Expired contract status auto-updated correctly")
                    else:
                        print(f"   ⚠️  Expected 'Expired' status, got '{expired_contract['status']}'")
            
            # Verify email fields are present
            contracts_with_email = [c for c in response if 'contact_email' in c]
            print(f"   Contracts with email field: {len(contracts_with_email)}/{len(response)}")
        
        return success

    def test_get_single_contract(self):
        """Test getting a single contract by ID"""
        if not self.created_contract_id:
            print("❌ Skipping single contract test - no contract ID available")
            return False
            
        return self.run_test(
            "Get Single Contract",
            "GET",
            f"contracts/{self.created_contract_id}",
            200
        )

    def test_update_contract(self):
        """Test updating a contract"""
        if not self.created_contract_id:
            print("❌ Skipping update test - no contract ID available")
            return False
            
        update_data = {
            "name": "Updated Test Service Agreement",
            "status": "Renewed"
        }
        
        return self.run_test(
            "Update Contract",
            "PUT",
            f"contracts/{self.created_contract_id}",
            200,
            data=update_data
        )

    def test_ai_document_analysis(self):
        """Test AI document analysis with sample contract text"""
        sample_text = """Service Agreement - This agreement is made on February 10, 2024, between Global Corp and Tech Innovations LLC. The contract term is 12 months from the effective date. Services include software development and maintenance as detailed in Schedule A."""
        
        analysis_data = {
            "document_text": sample_text
        }
        
        print("🤖 Testing AI Document Analysis...")
        print(f"   Sample text: {sample_text[:100]}...")
        
        success, response = self.run_test(
            "AI Document Analysis",
            "POST",
            "analyze-document",
            200,
            data=analysis_data
        )
        
        if success:
            contract_date = response.get('contract_date')
            contract_tenure = response.get('contract_tenure')
            expiry_date = response.get('expiry_date')
            error = response.get('error')
            
            if error:
                print(f"   ⚠️  AI Analysis returned error: {error}")
            else:
                print(f"   📅 Extracted contract date: {contract_date}")
                print(f"   📊 Extracted tenure: {contract_tenure}")
                print(f"   🗓️  Calculated expiry: {expiry_date}")
                
                # Validate expected results
                expected_date = "2024-02-10"
                expected_expiry = "2025-02-10"
                
                if contract_date == expected_date:
                    print("   ✅ Contract date extraction correct")
                else:
                    print(f"   ⚠️  Expected date {expected_date}, got {contract_date}")
                    
                if expiry_date == expected_expiry:
                    print("   ✅ Expiry date calculation correct")
                else:
                    print(f"   ⚠️  Expected expiry {expected_expiry}, got {expiry_date}")
        
        return success

    def test_delete_contract(self):
        """Test deleting a contract"""
        if not self.created_contract_id:
            print("❌ Skipping delete test - no contract ID available")
            return False
            
        return self.run_test(
            "Delete Contract",
            "DELETE",
            f"contracts/{self.created_contract_id}",
            200
        )

    def test_error_handling(self):
        """Test error handling for invalid requests"""
        print("\n🔍 Testing Error Handling...")
        
        # Test getting non-existent contract
        success1, _ = self.run_test(
            "Get Non-existent Contract",
            "GET",
            "contracts/invalid-id",
            404
        )
        
        # Test creating contract with invalid data
        invalid_data = {
            "name": "",  # Empty name should fail validation
            "client": "Test Client"
            # Missing required fields
        }
        
        success2, _ = self.run_test(
            "Create Invalid Contract",
            "POST",
            "contracts",
            422  # Validation error
        )
        
        return success1 and success2

def main():
    print("🚀 Starting Contract Management API Tests")
    print("=" * 50)
    
    tester = ContractAPITester()
    
    # Run all tests in sequence
    tests = [
        tester.test_health_check,
        tester.test_create_contract,
        tester.test_get_contracts,
        tester.test_get_single_contract,
        tester.test_update_contract,
        tester.test_ai_document_analysis,
        tester.test_delete_contract,
        tester.test_error_handling
    ]
    
    for test in tests:
        try:
            test()
        except Exception as e:
            print(f"❌ Test failed with exception: {str(e)}")
    
    # Print final results
    print("\n" + "=" * 50)
    print(f"📊 Final Results: {tester.tests_passed}/{tester.tests_run} tests passed")
    
    if tester.tests_passed == tester.tests_run:
        print("🎉 All tests passed!")
        return 0
    else:
        print("⚠️  Some tests failed - check logs above")
        return 1

if __name__ == "__main__":
    sys.exit(main())