from django.urls import path
from django.contrib.auth.views import LoginView, LogoutView

from . import views

urlpatterns = [

    # DONOR LOGIN
    path(
        'donorlogin/',
        LoginView.as_view(
            template_name='donor/donorlogin.html'
        ),
        name='donorlogin'
    ),

    # DONOR SIGNUP
    path(
        'donorsignup/',
        views.donor_signup_view,
        name='donorsignup'
    ),

    # DONOR DASHBOARD
    path(
        'donor-dashboard/',
        views.donor_dashboard_view,
        name='donor-dashboard'
    ),

    # DONATE BLOOD
    path(
        'donate-blood/',
        views.donate_blood_view,
        name='donate-blood'
    ),

    # DONATION HISTORY
    path(
        'donation-history/',
        views.donation_history_view,
        name='donation-history'
    ),

    # MAKE REQUEST
    path(
        'make-request/',
        views.make_request_view,
        name='make-request'
    ),

    # REQUEST HISTORY
    path(
        'request-history/',
        views.request_history_view,
        name='request-history'
    ),

    # DONOR SEARCH
    path(
        'donors/',
        views.donor_list_view,
        name='donor-list'
    ),

    # DONOR SEARCH API
    path(
        'api/donors/',
        views.donor_list_api,
        name='donor-list-api'
    ),

]