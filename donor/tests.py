from django.test import TestCase
from django.contrib.auth.models import User
from donor.models import Donor

class DonorFilterApiTestCase(TestCase):
    def setUp(self):
        # Create test users
        self.user1 = User.objects.create_user(
            username='donor1', password='password123', first_name='John', last_name='Doe'
        )
        self.user2 = User.objects.create_user(
            username='donor2', password='password123', first_name='Jane', last_name='Smith'
        )
        self.user3 = User.objects.create_user(
            username='donor3', password='password123', first_name='Bob', last_name='Johnson'
        )

        # Create test donors
        self.donor1 = Donor.objects.create(
            user=self.user1,
            bloodgroup='O+',
            address='Chennai',
            mobile='9876543210'
        )
        self.donor2 = Donor.objects.create(
            user=self.user2,
            bloodgroup='A+',
            address='Bangalore',
            mobile='8765432109'
        )
        self.donor3 = Donor.objects.create(
            user=self.user3,
            bloodgroup='O-',
            address='Chennai Suburban',
            mobile='7654321098'
        )

    def test_filter_none(self):
        """Empty filters should return all donors"""
        response = self.client.get('/donor/api/donors/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['donors']), 3)

    def test_filter_location_only(self):
        """Only location search should work (case-insensitive and substring match)"""
        response = self.client.get('/donor/api/donors/', {'location': 'chennai'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['donors']), 2)
        names = [d['name'] for d in data['donors']]
        self.assertIn('John Doe', names)
        self.assertIn('Bob Johnson', names)

    def test_filter_bloodgroup_only(self):
        """Only blood group search should work"""
        response = self.client.get('/donor/api/donors/', {'bloodgroup': 'O+'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['donors']), 1)
        self.assertEqual(data['donors'][0]['name'], 'John Doe')

    def test_filter_bloodgroup_case_insensitive(self):
        """Blood group search should be case-insensitive"""
        response = self.client.get('/donor/api/donors/', {'bloodgroup': 'o+'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['donors']), 1)
        self.assertEqual(data['donors'][0]['name'], 'John Doe')

    def test_filter_bloodgroup_trim_spaces(self):
        """Blood group and location should be trimmed of extra spaces"""
        response = self.client.get('/donor/api/donors/', {'location': '  chennai  ', 'bloodgroup': '  o+  '})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['donors']), 1)
        self.assertEqual(data['donors'][0]['name'], 'John Doe')

    def test_filter_location_and_bloodgroup(self):
        """Both location and blood group together should work"""
        response = self.client.get('/donor/api/donors/', {'location': 'chennai', 'bloodgroup': 'O-'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['donors']), 1)
        self.assertEqual(data['donors'][0]['name'], 'Bob Johnson')

    def test_filter_bloodgroup_url_encoded(self):
        """Properly handle URL encoded blood groups (O+ as O%2B)"""
        # Note: self.client.get automatically encodes parameters, but let's test hitting with raw query string
        response = self.client.get('/donor/api/donors/?bloodgroup=O%2B')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['donors']), 1)
        self.assertEqual(data['donors'][0]['name'], 'John Doe')

    def test_filter_bloodgroup_decoded_as_space(self):
        """Properly handle cases where '+' is decoded/sent as a space ' '"""
        response = self.client.get('/donor/api/donors/', {'bloodgroup': 'O '})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['donors']), 1)
        self.assertEqual(data['donors'][0]['name'], 'John Doe')

