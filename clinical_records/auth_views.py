"""
Authentication views for Clinical Records Service
"""
from django.shortcuts import redirect
from django.contrib.auth import logout
from django.contrib import messages


def logout_view(request):
    """
    Logout view
    """
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('login')