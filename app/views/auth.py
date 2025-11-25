from django.shortcuts import render, redirect
from django.http import HttpResponse
from app.models import User
from app.logic.auth import get_auth_token_for_user
from app.middleware.notice_middleware import generate_notice
import json


def sign_in(request):
    if request.authenticated:
        return redirect('/')
    
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        
        try:
            user = User.objects.get(email=email, password=password)
            response = redirect('/')
            response.set_cookie('authToken', get_auth_token_for_user(user))
            return response
        except User.DoesNotExist:
            return render(request, 'signin.html', {
                'notice': generate_notice('error', 'Invalid email or password')
            })
    
    return render(request, 'signin.html', {'notice': request.notice})


def sign_up(request):
    if request.method == 'POST':
        try:
            user = User.objects.create(
                email=request.POST.get('email'),
                password=request.POST.get('password'),  # In production, hash this
                name=request.POST.get('name')
            )
            response = redirect('/')
            response.set_cookie('authToken', get_auth_token_for_user(user))
            response.set_cookie('notice', 
                json.dumps(generate_notice('success', 'Successfully signed up. Welcome!')))
            return response
        except Exception as e:
            return render(request, 'signup.html', {
                'notice': generate_notice('error', f'Failed to sign up due to {str(e)}')
            })
    
    # Handle GET request
    return render(request, 'signup.html', {'notice': request.notice})


def sign_out(request):
    response = redirect('/sign-in')
    response.delete_cookie('authToken')
    return response

