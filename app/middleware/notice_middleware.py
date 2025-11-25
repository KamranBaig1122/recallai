import json
from django.utils.deprecation import MiddlewareMixin


def generate_notice(notice_type, message):
    return {'type': notice_type, 'message': message}


class NoticeMiddleware(MiddlewareMixin):
    def process_request(self, request):
        request.notice = None
        
        notice_cookie = request.COOKIES.get('notice')
        if notice_cookie:
            try:
                # Handle both string and dict formats
                if isinstance(notice_cookie, str):
                    request.notice = json.loads(notice_cookie)
                else:
                    request.notice = notice_cookie
            except (json.JSONDecodeError, ValueError, TypeError):
                pass
    
    def process_response(self, request, response):
        # Clear notice cookie after reading (if it was set)
        if hasattr(request, 'notice') and request.notice:
            # Don't delete if it was just set in the response
            pass
        return response

