import os
import re
import math
import pandas as pd
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User, Group
from django.contrib.auth.hashers import make_password
from django.db import transaction
from donor.models import Donor

class Command(BaseCommand):
    help = 'Dynamically imports 300+ student/donor records from an Excel (.xlsx) file into SQLite using high-performance Django ORM bulk insertions.'

    def add_arguments(self, parser):
        parser.add_argument(
            'excel_file', 
            nargs='?', 
            type=str, 
            default='donors.xlsx', 
            help='Path to the Excel file containing student/donor records'
        )

    def handle(self, *args, **options):
        excel_path = options['excel_file']

        self.stdout.write(self.style.WARNING(f"Initializing Excel donor import workflow..."))
        self.stdout.write(self.style.WARNING(f"Target Excel file: {excel_path}"))

        # 1. File existence validation
        if not os.path.exists(excel_path):
            raise CommandError(
                f"The Excel file '{excel_path}' does not exist.\n"
                f"Please upload/place the file or provide the correct path (e.g. python manage.py import_donors C:\\path\\to\\file.xlsx)"
            )

        # 2. Read spreadsheet
        try:
            # openpyxl engine is used for .xlsx files
            df = pd.read_excel(excel_path, dtype=str)
        except Exception as e:
            raise CommandError(f"Failed to read the Excel file: {str(e)}")

        total_rows = len(df)
        self.stdout.write(self.style.SUCCESS(f"Successfully loaded Excel sheet. Found {total_rows} records."))

        # 3. Dynamic Column Header Mapping (Case-insensitive fuzzy mapping)
        col_mapping = self.detect_columns(df.columns)
        self.log_detected_mappings(col_mapping)

        # Ensure we have minimum required fields to create a User/Donor account
        required_keys = ['first_name', 'mobile']
        missing_required = [k for k in required_keys if k not in col_mapping]
        if missing_required:
            raise CommandError(
                f"Could not map essential columns: {missing_required}. "
                f"Please ensure the Excel sheet contains columns for 'Name' and 'Mobile/Phone'."
            )

        # 4. Fetch existing records to prevent duplicates and enable safe caching
        self.stdout.write("Caching existing database records for de-duplication...")
        existing_usernames = set(User.objects.values_list('username', flat=True))
        existing_emails = {email.lower() for email in User.objects.values_list('email', flat=True) if email}
        existing_mobiles = {str(mobile).strip() for mobile in Donor.objects.values_list('mobile', flat=True) if mobile}

        # 5. Get or create the 'DONOR' group
        donor_group, _ = Group.objects.get_or_create(name='DONOR')

        # Accumulator lists for bulk insertions
        users_to_create = []
        donors_data_to_create = []
        
        imported_count = 0
        skipped_duplicates = 0
        failed_records = []

        # Default password for all imported donor accounts (to be changed by them)
        default_pwd_hash = make_password('Donor@123')

        # 6. Parse and validate each row
        self.stdout.write("Parsing and validating rows...")
        for idx, row in df.iterrows():
            row_num = idx + 2 # row number in typical Excel (1-indexed + header row)
            
            try:
                # Extract and split full name if only single 'name' is mapped
                raw_first_name = row[col_mapping['first_name']] if 'first_name' in col_mapping else None
                raw_last_name = row[col_mapping['last_name']] if 'last_name' in col_mapping else None
                
                if not raw_first_name or self.is_null(raw_first_name):
                    failed_records.append({
                        'row': row_num,
                        'reason': 'Name column is empty or null.',
                        'data': dict(row)
                    })
                    continue

                if 'last_name' not in col_mapping or not raw_last_name or self.is_null(raw_last_name):
                    first_name, last_name = self.split_name(raw_first_name)
                else:
                    first_name = str(raw_first_name).strip()[:30]
                    last_name = str(raw_last_name).strip()[:30]

                # Extract and normalize phone/mobile number (required)
                mobile_val = row[col_mapping['mobile']] if 'mobile' in col_mapping else None
                if not mobile_val or self.is_null(mobile_val):
                    failed_records.append({
                        'row': row_num,
                        'reason': 'Mobile number is empty or null.',
                        'data': dict(row)
                    })
                    continue
                mobile = self.clean_mobile(mobile_val)

                # Extract and clean email
                email = None
                if 'email' in col_mapping:
                    raw_email = row[col_mapping['email']]
                    if raw_email and not self.is_null(raw_email):
                        email = str(raw_email).strip().lower()

                # Extract register/roll number or student ID
                reg_num = None
                if 'register_number' in col_mapping:
                    raw_reg = row[col_mapping['register_number']]
                    if raw_reg and not self.is_null(raw_reg):
                        reg_num = str(raw_reg).strip()

                # Determine username (Use Register Number if available, else generate uniquely)
                if reg_num:
                    username = self.clean_username(reg_num)
                else:
                    username = self.generate_username_from_row(first_name, email, mobile, idx)

                # Extract and normalize remaining Donor profile fields
                bloodgroup = self.normalize_blood_group(row[col_mapping['bloodgroup']]) if 'bloodgroup' in col_mapping else 'O+'
                gender = self.normalize_gender(row[col_mapping['gender']]) if 'gender' in col_mapping else 'Male'
                address = str(row[col_mapping['address']]).strip()[:40] if 'address' in col_mapping and not self.is_null(row[col_mapping['address']]) else 'Not Provided'
                
                last_donation_date = None
                if 'last_donation_date' in col_mapping:
                    last_donation_date = self.parse_date(row[col_mapping['last_donation_date']])

                is_available = True
                if 'is_available' in col_mapping:
                    is_available = self.parse_boolean(row[col_mapping['is_available']])

                # 7. Check for duplicate entries
                is_duplicate = False
                dup_reason = []

                if username.lower() in existing_usernames:
                    is_duplicate = True
                    dup_reason.append(f"Username '{username}' already exists")
                if email and email.lower() in existing_emails:
                    is_duplicate = True
                    dup_reason.append(f"Email '{email}' already exists")
                if mobile in existing_mobiles:
                    is_duplicate = True
                    dup_reason.append(f"Mobile '{mobile}' already exists")

                if is_duplicate:
                    skipped_duplicates += 1
                    # Self-contained logging to avoid cluttering but inform about skips
                    self.stdout.write(
                        self.style.WARNING(f"Skipping Row {row_num}: Duplicate detected ({', '.join(dup_reason)}).")
                    )
                    continue

                # 8. Stash unique record for bulk processing and update in-memory cache to prevent self-duplicates
                existing_usernames.add(username.lower())
                if email:
                    existing_emails.add(email.lower())
                existing_mobiles.add(mobile)

                # Create user object instance (in-memory)
                new_user = User(
                    username=username,
                    first_name=first_name,
                    last_name=last_name,
                    email=email or '',
                    password=default_pwd_hash,
                    is_active=True
                )
                users_to_create.append(new_user)

                # Store additional donor fields to pair with the saved User object
                donors_data_to_create.append({
                    'bloodgroup': bloodgroup,
                    'gender': gender,
                    'address': address,
                    'mobile': mobile,
                    'last_donation_date': last_donation_date,
                    'is_available': is_available,
                    'row_num': row_num
                })

            except Exception as ex:
                failed_records.append({
                    'row': row_num,
                    'reason': f"Parsing error: {str(ex)}",
                    'data': dict(row)
                })

        # 9. Perform transactional bulk creations
        num_to_insert = len(users_to_create)
        if num_to_insert > 0:
            self.stdout.write(f"Executing bulk insertion for {num_to_insert} records...")
            try:
                with transaction.atomic():
                    # Create all User profiles
                    User.objects.bulk_create(users_to_create)
                    
                    # Since SQLite in Django 3.0 does not return populated primary keys on bulk_create,
                    # we retrieve the created User objects from the DB using their unique usernames.
                    usernames_list = [u.username for u in users_to_create]
                    db_users = {user.username: user for user in User.objects.filter(username__in=usernames_list)}
                    
                    # Create Donor profiles and map them directly using the retrieved database User objects
                    donor_instances = []
                    for user_inst, d_data in zip(users_to_create, donors_data_to_create):
                        saved_user = db_users.get(user_inst.username)
                        if saved_user:
                            donor_inst = Donor(
                                user=saved_user,
                                bloodgroup=d_data['bloodgroup'],
                                gender=d_data['gender'],
                                address=d_data['address'],
                                mobile=d_data['mobile'],
                                last_donation_date=d_data['last_donation_date'],
                                is_available=d_data['is_available']
                            )
                            donor_instances.append(donor_inst)

                    # Bulk create the Donor profiles
                    created_donors = Donor.objects.bulk_create(donor_instances)

                    # Add users to the 'DONOR' group using bulk relationship addition
                    # We pass the saved User objects containing database IDs
                    donor_group.user_set.add(*db_users.values())

                    imported_count = len(created_donors)

            except Exception as bulk_ex:
                self.stdout.write(self.style.ERROR(f"Database insertion failed: {str(bulk_ex)}"))
                raise CommandError("Bulk database transaction failed and rolled back.")
        else:
            self.stdout.write(self.style.WARNING("No new unique records found to insert."))

        # 10. Output beautiful, comprehensive execution summary
        self.stdout.write("\n" + "="*50)
        self.stdout.write(self.style.SUCCESS("IMPORT EXECUTION SUMMARY"))
        self.stdout.write("="*50)
        self.stdout.write(f"Total spreadsheet records read:  {total_rows}")
        self.stdout.write(self.style.SUCCESS(f"Successfully imported:         {imported_count}"))
        self.stdout.write(self.style.WARNING(f"Skipped duplicates:             {skipped_duplicates}"))
        self.stdout.write(self.style.ERROR(f"Failed validations/records:     {len(failed_records)}"))
        self.stdout.write("="*50)

        # Show detailed error logs for failure rows
        if failed_records:
            self.stdout.write("\n" + self.style.ERROR("FAILED RECORDS LIST:"))
            for item in failed_records:
                self.stdout.write(
                    self.style.ERROR(f"  - Row {item['row']}: {item['reason']}")
                )
            self.stdout.write("="*50 + "\n")

    # --- Helper methods for dynamic column mapping and fuzzy detection ---

    def detect_columns(self, sheet_columns):
        """
        Performs a dynamic case-insensitive fuzzy search on column names to match
        Excel headers with expected model fields.
        """
        mapping = {}
        for col in sheet_columns:
            cleaned = str(col).strip().lower().replace('_', ' ').replace('-', ' ')
            
            # Match First Name / Full Name
            if cleaned in ['name', 'full name', 'fullname', 'student name', 'donor name', 'first name', 'fname', 'first_name']:
                mapping['first_name'] = col
            # Match Last Name (if separate)
            elif cleaned in ['last name', 'lastname', 'lname', 'last_name']:
                mapping['last_name'] = col
            # Match Email
            elif cleaned in ['email', 'email id', 'emailid', 'email address', 'mail', 'email_id', 'email_address']:
                mapping['email'] = col
            # Match Phone / Mobile
            elif cleaned in ['mobile', 'mobile number', 'mobilenumber', 'phone', 'phone number', 'phonenumber', 'contact', 'contact number', 'cell', 'tel', 'mobile_number', 'phone_number']:
                mapping['mobile'] = col
            # Match Blood Group
            elif cleaned in ['blood group', 'bloodgroup', 'blood', 'bg', 'blood type', 'bloodtype', 'blood_group']:
                mapping['bloodgroup'] = col
            # Match Gender
            elif cleaned in ['gender', 'sex']:
                mapping['gender'] = col
            # Match Address / City
            elif cleaned in ['address', 'location', 'city', 'residence', 'address_line']:
                mapping['address'] = col
            # Match Donation Date
            elif cleaned in ['last donation date', 'last donation', 'donation date', 'last date', 'last_donation_date', 'last_donation']:
                mapping['last_donation_date'] = col
            # Match Availability
            elif cleaned in ['is available', 'available', 'availability', 'active', 'is_available']:
                mapping['is_available'] = col
            # Match Register / Student Roll Number
            elif cleaned in ['register number', 'reg no', 'regno', 'roll no', 'rollno', 'roll number', 'student id', 'studentid', 'register_number', 'reg_no', 'roll_no', 'roll_number', 'student_id']:
                mapping['register_number'] = col

        return mapping

    def log_detected_mappings(self, col_mapping):
        self.stdout.write("\nDetected column mapping:")
        for field, excel_col in col_mapping.items():
            self.stdout.write(f"  • {field.ljust(20)} --->  Excel: '{excel_col}'")
        self.stdout.write("")

    # --- Data Cleaning and Normalization Helpers ---

    def is_null(self, val):
        """Check if value is a Pandas NaN or standard null equivalents."""
        if val is None:
            return True
        if isinstance(val, float) and math.isnan(val):
            return True
        val_str = str(val).strip().lower()
        if val_str in ['nan', 'nat', '<na>', 'null', 'none', '']:
            return True
        return False

    def split_name(self, full_name):
        """Splits full name into First Name and Last Name safely."""
        parts = str(full_name).strip().split(' ', 1)
        if len(parts) == 2:
            return parts[0][:30], parts[1][:30]
        return parts[0][:30], ''

    def clean_mobile(self, val):
        """Cleans mobile number to digits only, removing floats (like .0) or symbols."""
        s = str(val).strip()
        if s.endswith('.0'):
            s = s[:-2]
        digits = re.sub(r'\D', '', s)
        return digits[:20]

    def clean_username(self, val):
        """Formats and sanitizes usernames to match Django specifications (max 150 chars)."""
        s = str(val).strip()
        if s.endswith('.0'):
            s = s[:-2]
        # Keep alphanumeric, @, ., +, -, _
        sanitized = re.sub(r'[^a-zA-Z0-9@\.\+\-_]', '', s)
        return sanitized[:150]

    def generate_username_from_row(self, first_name, email, mobile, idx):
        """Generates a clean, unique username base when register number is not available."""
        if email:
            base = email.split('@')[0]
        elif first_name:
            base = first_name
        else:
            base = 'donor'
            
        base_clean = re.sub(r'[^a-zA-Z0-9@\.\+\-_]', '', base).lower()
        if not base_clean:
            base_clean = 'donor'
            
        suffix = str(mobile)[-4:] if mobile and len(str(mobile)) >= 4 else str(idx)
        return f"{base_clean}_{suffix}"[:150]

    def normalize_blood_group(self, val):
        """Maps varying Excel blood group text directly to system validation constraints."""
        if self.is_null(val):
            return 'O+'
            
        bg = str(val).strip().upper()
        # Normalization transformations
        bg = bg.replace('POSITIVE', '+').replace('NEGATIVE', '-').replace('POS', '+').replace('NEG', '-').replace(' ', '')
        
        valid_groups = ['O+', 'O-', 'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-']
        if bg in valid_groups:
            return bg
            
        # Try substring matching (e.g. 'B POSITIVE' matching 'B+')
        for v in valid_groups:
            if v in bg:
                return v
        return 'O+' # default fallback

    def normalize_gender(self, val):
        """Maps Excel text to 'Male', 'Female', or 'Other' fields."""
        if self.is_null(val):
            return 'Male'
            
        g = str(val).strip().capitalize()
        if g in ['Male', 'Female', 'Other']:
            return g
            
        if g.startswith('M'):
            return 'Male'
        if g.startswith('F'):
            return 'Female'
        return 'Other'

    def parse_date(self, val):
        """Attempts parsing Excel float timestamp, standard dates, or strings to yyyy-mm-dd date format."""
        if self.is_null(val):
            return None
        try:
            # Check if Pandas datetime object
            if hasattr(val, 'date'):
                return val.date()
            # Parse string or timestamp
            parsed_dt = pd.to_datetime(val)
            if pd.isna(parsed_dt):
                return None
            return parsed_dt.date()
        except Exception:
            return None

    def parse_boolean(self, val):
        """Converts Excel yes/no, true/false, active/inactive, or 0/1 values to boolean flags."""
        if self.is_null(val):
            return True
        s = str(val).strip().lower()
        if s in ['true', '1', 'yes', 'y', 'active', 'available']:
            return True
        if s in ['false', '0', 'no', 'n', 'inactive', 'unavailable']:
            return False
        return True
