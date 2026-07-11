"""
Authentication Views for Clinical Records Service
"""
from django.shortcuts import render, redirect
from django.contrib.auth import logout
from django.contrib import messages


def logout_view(request):
    """Handle logout for both GET and POST requests"""
    if request.method == 'POST':
        logout(request)
        messages.success(request, 'You have been logged out successfully.')
        return redirect('login')
    else:
        # For GET requests, render a logout confirmation page
        return render(request, 'clinical_records/logout_confirm.html')
