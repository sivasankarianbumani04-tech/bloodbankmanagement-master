import re
import uuid
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group
from django.db import transaction
from donor.models import Donor

class Command(BaseCommand):
    help = 'Imports 57 parsed donor records into the SQLite database with robust normalization and duplicate checks.'

    def handle(self, *args, **options):
        raw_dataset = """ARAVINDHAN A | O + | Chennai | Male | 7010595984
DHANUSH J | None | Chennai | Male |
DINESH KARTHICK K | A1 | Chennai | Male | 9080926342
GOWRI SHANKAR R | None | Chennai | Male |
HARSHIT | B+ | Chennai | Male | 8619084280
HARSHITHA S | O+ve | Chennai | Male | 6379763001
HEMA BHARATHI B | B+ve | Thiruvalangadu | Male | 9840755091
INDHULEGA N | A1+ | Chennai | Male | 8925281131
JACK SHALOM G | A+ | Chennai | Male | 9445913384
JAISUDHAN A | B+ | Chennai | Male | 9342797876
JAYAKUMAR S | A1+ | Chennai | Male | 9080001257
JAYARAJ N | B + | Chennai | Male | 7094469361
JEEVITHRA R | O+ve | Chennai | Male | 9940282178
JENITT B | A + | Chennai | Male | 9445150563
JESSICA MONAL B | B+ve | Chennai | Male | 8148242908
KARTHIKA K | O+ | Sekkarakudi | Male | 9363776399
KAUSHIK P | A+ | Chennai | Male | 8825650559
KAVI PRIYA G | O+ ve | Chennai | Female | 9962399016
KAVITHA S | O+ve | Chennai | Male | 8098794844
KUMAR A | A+ve | Chennai | Male | 8122010734
LAKSHANYA N | A postive | Thiruninravur | Male | 9094710098
LAWRENCE A | A+ | Chennai | Male | 8122031081
LOGASHREE P | B+ | Thirunindravur | Female | 8807965355
LOKESH D | A+ve | Chennai | Male | 6382456147
MADESH A | o+ | Chennai | Male | 7358739321
MANISHA R | A-ve | Chennai | Male | 9500079092
MOHAMMED GAYAZ C | AB+ve | Chennai | Male | 6385333431
MURALITHARAN J | O+ | Ariyalur | Male | 7305623147
NATHEEM AHAMED S | O positive | R K Pet | Male | 8610159382
R.NAVEEN | B+ | Chennai | Male | 7418035675
NAVEEN S R | B+ | Chennai | Male | 9444480017
NIVETHA.V | B+ | Chennai | Female | 8122829038
V.NIVETHA | B+ve | Ranipet | Female |
PRABHAKARAN H | A+ | Avadi | Male | 6374569434
PRADEEP ARJUNAN | B+ | Avadi | Male | 9487455004
K.PRIYANKA | AB + | Arakkonam | Female | 9025643183
R PRIYANKA | A -ve | Chennai | Female | 8056316554
RUSHIL.N | A+ group | Ranipet | Male | 9952029682
SADHANA S | O+ | Chennai | Male | 6381519775
SARATHKUMAR.V | A+ve | Chennai | Male | 9025234246
L. SARULATHA | A+ | Chennai | Male | 8072829537
SATHANA R | B+ | Chennai | Male | 7708694434
SELVA GANESH S | O+ve | Chennai | Male | 7010539375
E. SHANTHINI PRIYA | O+ | Chennai | Female | 8124195910
S SHARUKESH | AB + | Chennai | Male | 8825730865
SHIVANI R T | O+ve | Chennai | Male | 9940857673
A.SIVASANKARI | O+ | Chennai | Male | 8695759535
SONALEE M | B+ | Chennai | Male | 7358001785
SURYA D | A1+ | Chennai | Male | 7397552312
J.V.SURYA PRAKASH | O+ | Chennai | Male | 7845728473
SUVETHA V | O+ | Chennai | Male | 6382076626
THAMINI K | B +ve | Avadi | Male | 9042071224
K.THIMMARAYAN | O+ | Chennai | Male | 6374483602
VIGNESH KUMAR V | B+ve | Chennai | Male | 8015750548
R. VIJAYA SREE | B+ve | Chennai | Male | 7200370324
V. VISHAL | B+ | Chennai | Male | 9003299718
YATHRA.S | B+ve | Chennai | Male | 6379299637"""

        self.stdout.write(self.style.WARNING("Starting bulk donor database injection..."))

        def normalize_blood_group(bg):
            if not bg or bg.strip().lower() == 'none' or bg.strip() == '':
                return "Unknown"
            
            s = bg.upper().strip().replace(' ', '')
            s = s.replace('POSITIVE', '+').replace('NEGATIVE', '-').replace('POS', '+').replace('NEG', '-').replace('VE', '')
            
            # Standardize A1 to A
            if 'A1' in s:
                s = s.replace('A1', 'A')
                
            valid_groups = ['O+', 'O-', 'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-']
            if s in valid_groups:
                return s
                
            # Substring checks
            for v in valid_groups:
                if v in s:
                    return v
                    
            if 'AB' in s:
                return 'AB-' if '-' in s else 'AB+'
            elif 'A' in s:
                return 'A-' if '-' in s else 'A+'
            elif 'B' in s:
                return 'B-' if '-' in s else 'B+'
            elif 'O' in s:
                return 'O-' if '-' in s else 'O+'
                
            return "Unknown"

        def normalize_gender(g):
            if not g:
                return "Male"
            g_clean = g.strip().capitalize()
            if g_clean in ['Male', 'Female']:
                return g_clean
            if g_clean.startswith('M'):
                return 'Male'
            if g_clean.startswith('F'):
                return 'Female'
            return 'Male'

        # Cache existing records from DB to prevent duplicates
        existing_usernames = set(User.objects.values_list('username', flat=True))
        existing_mobiles = set(Donor.objects.exclude(mobile="").values_list('mobile', flat=True))

        donor_group, _ = Group.objects.get_or_create(name='DONOR')
        success_count = 0
        skipped_count = 0
        failed_count = 0

        for idx, line in enumerate(raw_dataset.strip().split('\n')):
            if not line.strip():
                continue
            
            parts = [x.strip() for x in line.split('|')]
            name = parts[0]
            
            raw_bg = parts[1] if len(parts) > 1 else 'None'
            bg = normalize_blood_group(raw_bg)
            
            raw_city = parts[2] if len(parts) > 2 else 'Chennai'
            city = raw_city.strip().title()
            
            raw_gender = parts[3] if len(parts) > 3 else 'Male'
            gender = normalize_gender(raw_gender)
            
            mobile = parts[4].replace(".0", "").replace(" ", "").strip() if len(parts) > 4 else ""
            if mobile.lower() == 'none' or mobile == '':
                mobile = ""
                
            # Check duplicate phone numbers if mobile is not empty
            if mobile != "":
                if mobile in existing_usernames or mobile in existing_mobiles:
                    self.stdout.write(self.style.WARNING(f"[SKIP] Row {idx+1}: Duplicate phone number skipped -> {name} ({mobile})"))
                    skipped_count += 1
                    continue
                    
            # Generate unique username for Django user model
            if mobile == "":
                username = f"nophone_{uuid.uuid4().hex[:8]}"
            else:
                username = mobile
                
            try:
                # Add to in-memory caches to prevent duplicates within this run
                existing_usernames.add(username)
                if mobile != "":
                    existing_mobiles.add(mobile)
                    
                name_parts = name.split()
                if len(name_parts) > 1:
                    first_name = " ".join(name_parts[:-1])
                    last_name = name_parts[-1]
                else:
                    first_name = name
                    last_name = ""
                    
                with transaction.atomic():
                    # Create standard Django User credentials
                    user = User.objects.create(
                        username=username,
                        first_name=first_name[:30],
                        last_name=last_name[:30]
                    )
                    user.set_password('donor123')
                    user.save()
                    
                    # Link User to DONOR Group
                    donor_group.user_set.add(user)
                    
                    # Create Donor record
                    Donor.objects.create(
                        user=user,
                        bloodgroup=bg,
                        address=city,
                        gender=gender,
                        mobile=mobile
                    )
                    
                self.stdout.write(self.style.SUCCESS(f"[INSERT] Successfully entered: {name.ljust(25)} | {bg.ljust(7)} | {city.ljust(15)} | {gender.ljust(7)} | {mobile if mobile else '<Empty>'}"))
                success_count += 1
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"[ERROR] Row {idx+1} failed ({name}): {str(e)}"))
                failed_count += 1

        self.stdout.write("\n" + "="*50)
        self.stdout.write(self.style.SUCCESS("BULK IMPORT EXECUTION COMPLETE"))
        self.stdout.write("="*50)
        self.stdout.write(self.style.SUCCESS(f"Successfully Inserted: {success_count}"))
        self.stdout.write(self.style.WARNING(f"Skipped Duplicates:    {skipped_count}"))
        if failed_count > 0:
            self.stdout.write(self.style.ERROR(f"Failed Records:        {failed_count}"))
        self.stdout.write("="*50)
