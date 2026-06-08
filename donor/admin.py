from django.contrib import admin
from .models import Donor, BloodDonate

@admin.register(Donor)
class DonorAdmin(admin.ModelAdmin):
    list_display = ('id', 'get_name', 'bloodgroup', 'gender', 'mobile', 'address', 'last_donation_date', 'is_available')
    list_filter = ('bloodgroup', 'gender', 'is_available')
    search_fields = ('user__first_name', 'user__last_name', 'user__username', 'mobile', 'address')
    list_editable = ('is_available',)
    ordering = ('id',)

    def get_name(self, obj):
        return f"{obj.user.first_name} {obj.user.last_name}".strip() or obj.user.username
    get_name.short_description = 'Donor Name'

@admin.register(BloodDonate)
class BloodDonateAdmin(admin.ModelAdmin):
    list_display = ('id', 'donor', 'bloodgroup', 'unit', 'disease', 'status', 'date')
    list_filter = ('bloodgroup', 'status', 'date')
    search_fields = ('donor__user__first_name', 'donor__user__last_name', 'disease')
    ordering = ('-date',)

