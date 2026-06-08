from django.shortcuts import render,redirect,reverse
from . import forms,models
from django.db.models import Sum,Q
from django.contrib.auth.models import Group
from django.http import HttpResponseRedirect
from django.contrib.auth.decorators import login_required,user_passes_test
from django.conf import settings
from datetime import date, timedelta
from django.core.mail import send_mail
from django.contrib.auth.models import User

from blood import forms as bforms
from blood import models as bmodels



# DONOR SIGNUP
def donor_signup_view(request):

    userForm=forms.DonorUserForm()
    donorForm=forms.DonorForm()

    mydict={
        'userForm':userForm,
        'donorForm':donorForm
    }

    if request.method=='POST':

        userForm=forms.DonorUserForm(request.POST)

        donorForm=forms.DonorForm(
            request.POST,
            request.FILES
        )

        if userForm.is_valid() and donorForm.is_valid():

            # SAVE USER
            user=userForm.save(commit=False)

            # HASH PASSWORD
            user.set_password(user.password)

            user.save()

            # SAVE DONOR
            donor=donorForm.save(commit=False)

            donor.user=user

            donor.bloodgroup=donorForm.cleaned_data['bloodgroup']

            donor.save()

            # ADD USER TO DONOR GROUP
            my_donor_group=Group.objects.get_or_create(
                name='DONOR'
            )

            my_donor_group[0].user_set.add(user)

            return redirect('donorlogin')

    return render(
        request,
        'donor/donorsignup.html',
        context=mydict
    )



# DONOR DASHBOARD
def donor_dashboard_view(request):

    donor=models.Donor.objects.get(user_id=request.user.id)

    dict={

        'requestpending':
        bmodels.BloodRequest.objects.all()
        .filter(request_by_donor=donor)
        .filter(status='Pending')
        .count(),

        'requestapproved':
        bmodels.BloodRequest.objects.all()
        .filter(request_by_donor=donor)
        .filter(status='Approved')
        .count(),

        'requestmade':
        bmodels.BloodRequest.objects.all()
        .filter(request_by_donor=donor)
        .count(),

        'requestrejected':
        bmodels.BloodRequest.objects.all()
        .filter(request_by_donor=donor)
        .filter(status='Rejected')
        .count(),
    }

    return render(
        request,
        'donor/donor_dashboard.html',
        context=dict
    )



# DONATE BLOOD
def donate_blood_view(request):

    donation_form=forms.DonationForm()

    if request.method=='POST':

        donation_form=forms.DonationForm(request.POST)

        if donation_form.is_valid():

            blood_donate=donation_form.save(commit=False)

            blood_donate.bloodgroup=donation_form.cleaned_data['bloodgroup']

            donor=models.Donor.objects.get(user_id=request.user.id)

            blood_donate.donor=donor

            blood_donate.save()

            return redirect('donation-history')

    return render(
        request,
        'donor/donate_blood.html',
        {
            'donation_form':donation_form
        }
    )



# DONATION HISTORY
def donation_history_view(request):

    donor=models.Donor.objects.get(user_id=request.user.id)

    donations=models.BloodDonate.objects.all().filter(
        donor=donor
    )

    return render(
        request,
        'donor/donation_history.html',
        {
            'donations':donations
        }
    )



# MAKE BLOOD REQUEST
def make_request_view(request):

    request_form=bforms.RequestForm()

    if request.method=='POST':

        request_form=bforms.RequestForm(request.POST)

        if request_form.is_valid():

            blood_request=request_form.save(commit=False)

            blood_request.bloodgroup=request_form.cleaned_data['bloodgroup']

            donor=models.Donor.objects.get(user_id=request.user.id)

            blood_request.request_by_donor=donor

            blood_request.save()

            return redirect('request-history')

    return render(
        request,
        'donor/makerequest.html',
        {
            'request_form':request_form
        }
    )



# REQUEST HISTORY
def request_history_view(request):

    donor=models.Donor.objects.get(user_id=request.user.id)

    blood_request=bmodels.BloodRequest.objects.all().filter(
        request_by_donor=donor
    )

    return render(
        request,
        'donor/request_history.html',
        {
            'blood_request':blood_request
        }
    )



# SEARCH DONORS BY CITY + BLOOD GROUP
def donor_list_view(request):

    city=request.GET.get('city')

    bloodgroup=request.GET.get('bloodgroup')

    donors=models.Donor.objects.all()

    # FILTER BY ADDRESS/CITY
    if city:

        donors=donors.filter(
            address__icontains=city
        )

    # FILTER BY BLOOD GROUP
    if bloodgroup:

        donors=donors.filter(
            bloodgroup=bloodgroup
        )

    return render(
        request,
        'donor/donor_list.html',
        {
            'donors':donors,
            'selected_city':city,
            'selected_bloodgroup':bloodgroup,
        }
    )

from django.http import JsonResponse

def donor_list_api(request):
    import urllib.parse
    
    # 1. Print request query params in backend terminal for debugging
    raw_location = request.GET.get('location', '')
    raw_bloodgroup = request.GET.get('bloodgroup', '')
    print(f"[Backend Debug] Raw Request Query Params -> location: '{raw_location}', bloodgroup: '{raw_bloodgroup}'")

    # 2. Decode request parameters properly
    decoded_location = urllib.parse.unquote(raw_location)
    decoded_bloodgroup = urllib.parse.unquote(raw_bloodgroup)

    # 3. Trim extra spaces from location and blood group
    location = decoded_location.strip()
    bloodgroup = decoded_bloodgroup.strip()

    # 4. Properly handle URL encoded blood groups (O+ becomes O%2B) and '+' decoded as space
    # If the stripped bloodgroup doesn't end with '+' or '-', but the raw or decoded parameter had a space or '+' at the end
    if bloodgroup and not (bloodgroup.endswith('+') or bloodgroup.endswith('-')):
        if '+' in decoded_bloodgroup or decoded_bloodgroup.endswith(' ') or decoded_bloodgroup.rstrip().endswith(' '):
            bloodgroup += '+'

    print(f"[Backend Debug] Processed Query Params -> location: '{location}', bloodgroup: '{bloodgroup}'")

    # 5. Make filtering case-insensitive and support all combinations
    if location and bloodgroup:
        donors = models.Donor.objects.filter(
            address__icontains=location,
            bloodgroup__iexact=bloodgroup
        )
    elif location:
        donors = models.Donor.objects.filter(
            address__icontains=location
        )
    elif bloodgroup:
        donors = models.Donor.objects.filter(
            bloodgroup__iexact=bloodgroup
        )
    else:
        donors = models.Donor.objects.all()

    donor_data = []
    for d in donors:
        donor_data.append({
            'id': d.id,
            'name': d.get_name,
            'bloodgroup': d.bloodgroup,
            'location': d.address,
            'gender': d.gender,
            'mobile': d.mobile,
            'last_donation_date': d.last_donation_date.strftime('%Y-%m-%d') if d.last_donation_date else None,
            'is_available': d.is_available,
        })
    
    return JsonResponse({'donors': donor_data})