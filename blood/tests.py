from django.test import TestCase
from django.contrib.auth.models import User, Group
from donor.models import Donor

class BulkImportApiTestCase(TestCase):
    def setUp(self):
        # Create an admin user for testing and logging in
        self.admin_user = User.objects.create_superuser(
            username='admin', password='adminpassword', email='admin@bloodbank.com'
        )
        self.client.login(username='admin', password='adminpassword')
        
        # Ensure the 'DONOR' group exists in the DB
        Group.objects.get_or_create(name='DONOR')

    def test_bulk_import_valid_data(self):
        """API should successfully import valid donor records, normalize blood groups, and prevent duplicate mobiles"""
        payload = {
            'donors': [
                {
                    'name': 'ABINESH S',
                    'bloodgroup': '0+ve',
                    'address': 'CHENNAI',
                    'gender': 'Male',
                    'mobile': '8122545886'
                },
                {
                    'name': 'ALTHAF M',
                    'bloodgroup': 'O+',
                    'address': 'Arakkonam',
                    'gender': 'Male',
                    'mobile': '8248841987'
                }
            ]
        }
        
        response = self.client.post(
            '/api/donors/bulk-import',
            data=payload,
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        res_data = response.json()
        self.assertTrue(res_data['success'])
        self.assertEqual(res_data['success_count'], 2)
        self.assertEqual(res_data['failed_count'], 0)
        
        # Check DB states
        self.assertEqual(Donor.objects.count(), 2)
        donor1 = Donor.objects.get(mobile='8122545886')
        self.assertEqual(donor1.user.first_name, 'ABINESH')
        self.assertEqual(donor1.user.last_name, 'S')
        self.assertEqual(donor1.bloodgroup, 'O+') # Normalized from 0+ve
        
        donor2 = Donor.objects.get(mobile='8248841987')
        self.assertEqual(donor2.bloodgroup, 'O+')

    def test_bulk_import_validation_and_duplicates(self):
        """API should reject duplicate phone numbers and invalid input fields"""
        # Create a pre-existing donor with mobile '8015889225'
        existing_user = User.objects.create_user(username='8015889225', password='password')
        Donor.objects.create(user=existing_user, mobile='8015889225', address='Chennai', bloodgroup='B+')

        payload = {
            'donors': [
                {
                    'name': 'ANBUNILA M',
                    'bloodgroup': 'B+',
                    'address': 'Nagapattinam',
                    'gender': 'Male',
                    'mobile': '8015889225' # Duplicate mobile number
                },
                {
                    'name': 'INVALID DONOR',
                    'bloodgroup': 'X+ve', # Invalid blood group
                    'address': '', # Missing address
                    'gender': 'Unknown', # Invalid gender
                    'mobile': '123' # Invalid phone length
                }
            ]
        }

        response = self.client.post(
            '/api/donors/bulk-import',
            data=payload,
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        res_data = response.json()
        self.assertTrue(res_data['success'])
        self.assertEqual(res_data['success_count'], 0)
        self.assertEqual(res_data['failed_count'], 2)
        
        # Check errors in failed list
        failed_records = res_data['failed_records']
        
        # Duplicate error check
        dup_record = failed_records[0]
        self.assertEqual(dup_record['record']['mobile'], '8015889225')
        self.assertIn('already registered', dup_record['errors'][0])
        
        # Validation error check
        val_record = failed_records[1]
        errors = val_record['errors']
        self.assertTrue(any('City/Address is required' in e for e in errors))
        self.assertTrue(any("Invalid blood group" in e for e in errors))
        self.assertTrue(any("Gender must be 'Male', 'Female', or 'Other'" in e for e in errors))

    def test_unauthenticated_access(self):
        """API should redirect or deny access to unauthenticated requests"""
        self.client.logout()
        response = self.client.post(
            '/api/donors/bulk-import',
            data={'donors': []},
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 302) # Redirect to login page

