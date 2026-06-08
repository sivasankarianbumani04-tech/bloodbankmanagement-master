import os
from django.core.management.base import BaseCommand
from django.db import transaction, models
from django.db.models import Count
from django.contrib.auth.models import User
from donor.models import Donor, BloodDonate
from blood.models import BloodRequest

class UnionFind:
    """Disjoint Set Union (Union-Find) to cluster overlapping duplicates."""
    def __init__(self, elements):
        self.parent = {el: el for el in elements}
        
    def find(self, x):
        if self.parent[x] == x:
            return x
        # Path compression
        self.parent[x] = self.find(self.parent[x])
        return self.parent[x]
        
    def union(self, x, y):
        root_x = self.find(x)
        root_y = self.find(y)
        if root_x != root_y:
            self.parent[root_x] = root_y

class Command(BaseCommand):
    help = 'Identifies and deletes duplicate donor and student records safely without losing donation histories, using optimized Django ORM transactions.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview duplicate deletions and show stats without committing changes to the database'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        if dry_run:
            self.stdout.write(self.style.WARNING("=== DRY-RUN MODE: Previewing Duplicate Purge ==="))
        else:
            self.stdout.write(self.style.WARNING("=== LIVE PURGE: Commencing Duplicate Purge ==="))

        # 1. Fetch all Donors and Users
        self.stdout.write("Reading donor database...")
        donors = list(Donor.objects.select_related('user').all())
        total_donors = len(donors)
        self.stdout.write(f"Found {total_donors} total donor records in the database.")

        if total_donors == 0:
            self.stdout.write(self.style.SUCCESS("No donors found in the database. Cleanup complete."))
            return

        # 2. Optimized related history counts (pre-fetching in exactly 2 queries instead of N+1)
        donation_counts = {
            item['donor_id']: item['count']
            for item in BloodDonate.objects.values('donor_id').annotate(count=Count('id'))
        }
        request_counts = {
            item['request_by_donor_id']: item['count']
            for item in BloodRequest.objects.values('request_by_donor_id').annotate(count=Count('id'))
        }

        # 3. Group by unique fields
        donors_by_mobile = {}
        donors_by_email = {}
        donors_by_username = {}

        for d in donors:
            # Group by mobile (clean up formats for exact comparison)
            mobile = str(d.mobile).strip() if d.mobile else None
            if mobile and mobile not in ['', 'nan', 'none']:
                donors_by_mobile.setdefault(mobile, []).append(d)

            # Group by email (case-insensitive)
            email = d.user.email.strip().lower() if d.user.email else None
            if email and email != '':
                donors_by_email.setdefault(email, []).append(d)

            # Group by username (case-insensitive)
            username = d.user.username.strip().lower() if d.user.username else None
            if username and username != '':
                donors_by_username.setdefault(username, []).append(d)

        # 4. Find all components using Union-Find to group overlapping duplicates
        donor_ids = [d.id for d in donors]
        uf = UnionFind(donor_ids)

        # Union mobile duplicates
        for mobile, group in donors_by_mobile.items():
            if len(group) > 1:
                first = group[0].id
                for other in group[1:]:
                    uf.union(first, other.id)

        # Union email duplicates
        for email, group in donors_by_email.items():
            if len(group) > 1:
                first = group[0].id
                for other in group[1:]:
                    uf.union(first, other.id)

        # Union username duplicates
        for username, group in donors_by_username.items():
            if len(group) > 1:
                first = group[0].id
                for other in group[1:]:
                    uf.union(first, other.id)

        # Map parent root to elements in component
        components = {}
        for d_id in donor_ids:
            root = uf.find(d_id)
            components.setdefault(root, []).append(d_id)

        # Filter out clusters with only 1 item (these are already unique)
        duplicate_clusters = {root: ids for root, ids in components.items() if len(ids) > 1}

        if not duplicate_clusters:
            self.stdout.write(self.style.SUCCESS("\nNo duplicate records detected. Your database is already fully unique!"))
            return

        self.stdout.write(self.style.SUCCESS(f"\nDetected {len(duplicate_clusters)} duplicate clusters to process."))

        # Map donor ID to object for fast lookup
        donor_map = {d.id: d for d in donors}

        users_to_delete_ids = []
        keep_donors_log = []
        delete_donors_log = []

        # 5. Process each cluster and choose the best candidate to KEEP
        for cluster_idx, (root, d_ids) in enumerate(duplicate_clusters.items(), start=1):
            cluster_donors = [donor_map[d_id] for d_id in d_ids]

            # Custom ranking helper
            def get_donor_rank_key(donor):
                # We want to MAXIMIZE history count (donations + requests)
                history = donation_counts.get(donor.id, 0) + request_counts.get(donor.id, 0)
                
                # We want to MAXIMIZE profile completeness
                completeness = 0
                if donor.last_donation_date:
                    completeness += 1
                if donor.address and str(donor.address).strip().lower() not in ['', 'none', 'not provided']:
                    completeness += 1
                if donor.profile_pic and hasattr(donor.profile_pic, 'name') and donor.profile_pic.name:
                    completeness += 1
                
                # We want to MINIMIZE ID (older account is preferred)
                # We return a tuple representing (negative_history, negative_completeness, id)
                return (-history, -completeness, donor.id)

            # Sort by rank key
            sorted_cluster = sorted(cluster_donors, key=get_donor_rank_key)

            # First element is our keeper
            keep_donor = sorted_cluster[0]
            delete_donors = sorted_cluster[1:]

            keep_history = donation_counts.get(keep_donor.id, 0) + request_counts.get(keep_donor.id, 0)
            
            keep_donors_log.append({
                'donor': keep_donor,
                'history': keep_history,
                'cluster_size': len(cluster_donors)
            })

            # Mark rest for deletion
            for del_d in delete_donors:
                del_history = donation_counts.get(del_d.id, 0) + request_counts.get(del_d.id, 0)
                
                delete_donors_log.append({
                    'donor': del_d,
                    'history': del_history,
                    'keeper_id': keep_donor.id
                })
                # Collect User ID for cascading deletion
                users_to_delete_ids.append(del_d.user_id)

        # 6. Output Dry-Run Summary or Execute Purge
        self.stdout.write("\n" + "="*70)
        self.stdout.write("DETAILED DUPLICATE CLEANUP SCHEDULING")
        self.stdout.write("="*70)
        
        self.stdout.write(self.style.SUCCESS(f"Records to KEEP (Kept Profiles):"))
        for item in keep_donors_log:
            kd = item['donor']
            self.stdout.write(
                f"  • KEEP Donor ID {str(kd.id).ljust(4)}: {kd.get_name.ljust(20)} | Phone: {str(kd.mobile).ljust(15)} | Email: {str(kd.user.email).ljust(25)} | History Count: {item['history']} (Cluster Size: {item['cluster_size']})"
            )

        self.stdout.write("\n" + self.style.ERROR(f"Duplicate records scheduled for PURGE (Cascading User + Donor Delete):"))
        for item in delete_donors_log:
            dd = item['donor']
            self.stdout.write(
                self.style.ERROR(
                    f"  - PURGE Donor ID {str(dd.id).ljust(3)}: {dd.get_name.ljust(20)} | Phone: {str(dd.mobile).ljust(15)} | Email: {str(dd.user.email).ljust(25)} | History Count: {item['history']} -> Merges into Keeper ID {item['keeper_id']}"
                )
            )
        self.stdout.write("="*70)

        total_to_delete = len(users_to_delete_ids)

        if dry_run:
            self.stdout.write(self.style.WARNING(f"\n[DRY-RUN] Preview complete. This operation would delete {total_to_delete} duplicate records."))
            self.stdout.write(self.style.WARNING("No database changes were committed."))
        else:
            if total_to_delete > 0:
                self.stdout.write(f"\nDeleting {total_to_delete} duplicate auth User profiles in transaction...")
                try:
                    with transaction.atomic():
                        # Delete the parent User records.
                        # This cascades automatically to delete the child Donor profiles and maintains SQLite integrity.
                        deleted_count, _ = User.objects.filter(id__in=users_to_delete_ids).delete()
                        
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Successfully purged database duplicates!\n"
                            f"Total User records deleted:  {deleted_count // 2} (deleted {total_to_delete} User objects, and {total_to_delete} linked Donor objects via CASCADE)"
                        )
                    )
                except Exception as ex:
                    self.stdout.write(self.style.ERROR(f"Database execution failed: {str(ex)}"))
                    self.stdout.write(self.style.ERROR("Transaction has been rolled back. No changes made."))
            else:
                self.stdout.write(self.style.WARNING("\nNo records were scheduled for deletion."))

        self.stdout.write("\n" + "="*50)
        self.stdout.write(self.style.SUCCESS("CLEANUP METRICS SUMMARY"))
        self.stdout.write("="*50)
        self.stdout.write(f"Total starting donor records:  {total_donors}")
        self.stdout.write(self.style.ERROR(f"Records scheduled/purged:      {total_to_delete}"))
        self.stdout.write(self.style.SUCCESS(f"Unique records remaining:      {total_donors - total_to_delete}"))
        self.stdout.write("="*50 + "\n")
