from django.db import connection
from django.shortcuts import redirect
from django.urls import resolve, Resolver404
from django.http import HttpResponseForbidden

import time
import threading
from collections import defaultdict
from contextlib import contextmanager
import sentry_sdk


request_metrics = defaultdict(list)

# Thread-local storage for query times
_local = threading.local()

@contextmanager
def track_db_time():
    _local.db_time = 0.0
    def execute_wrapper(execute, sql, params, many, context):
        start = time.time()
        try:
            return execute(sql, params, many, context)
        finally:
            _local.db_time += time.time() - start
    
    with connection.execute_wrapper(execute_wrapper):
        yield
        

class RequestPerformanceMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.skip_methods = {'HEAD', 'OPTIONS'}

    def get_pattern_name(self, request):
        if request.method in self.skip_methods:
            return None
            
        try:
            resolver_match = getattr(request, 'resolver_match', None) or resolve(request.path)
            # Normalize all feed endpoints to a single path
            if resolver_match.func.__name__ == 'feed':
                return f"{request.method} feed/"
            return f"{request.method} {resolver_match.route}"
        except Resolver404:
            return None
        
    def __call__(self, request):
        endpoint = self.get_pattern_name(request)
        if endpoint is None:
            return self.get_response(request)

        start_time = time.time()
        
        with track_db_time():
            response = self.get_response(request)
            db_time = getattr(_local, 'db_time', 0.0)

        total_time = time.time() - start_time
        
        # Direct write to shared dictionary without locks
        metrics = request_metrics[endpoint]
        metrics.append({
            'total_time': total_time,
            'db_time': db_time,
            'compute_time': total_time - db_time,
            'timestamp': start_time
        })
        
        # Non-thread-safe list trimming
        if len(metrics) > 50:
            del metrics[:-50]

        return response
    

class LongRequestMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.threshold = 15  # seconds

    def __call__(self, request):
        start_time = time.time()
        response = self.get_response(request)
        duration = time.time() - start_time
        
        if duration > self.threshold:
            # Capture the long-running request in Sentry
            with sentry_sdk.push_scope() as scope:
                scope.set_extra("request_duration", duration)
                scope.set_extra("path", request.path)
                scope.set_extra("method", request.method)
                sentry_sdk.capture_message(
                    f"Long running request detected: {duration:.2f}s",
                    level="warning"
                )
        
        return response


class BearPassportMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.passport_cookie = 'bear_passport'
        self.protected_paths = ['/managed-challenge-test/']

    def __call__(self, request):
        if not any(request.path.startswith(protected) for protected in self.protected_paths):
            return self.get_response(request)

        # Check if this is a redirect attempt
        is_passport_check = request.GET.get('passport_check')
        
        if not request.COOKIES.get(self.passport_cookie):
            if is_passport_check:
                # We already tried setting a cookie and failed
                return HttpResponseForbidden('This site requires cookies to be enabled.')
            
            # First visit - try setting the cookie
            response = redirect(f"{request.path}?passport_check=grrr")
            response.set_cookie(self.passport_cookie, 'true', max_age=365*24*60*60)
            return response

        return self.get_response(request)