from functools import wraps

from flask import abort, request


def same_origin_required(view):
    """Reject cross-origin requests using the Origin/Referer header.

    Why: Flask-WTF CSRFProtect would require touching every existing form
    template; this is a narrower mitigation for new POST endpoints (JSON or
    form) where we own both server and client and the client always runs on
    the same origin.
    """
    @wraps(view)
    def wrapped(*args, **kwargs):
        origin = request.headers.get('Origin') or request.headers.get('Referer', '')
        if not origin:
            abort(403, description='Missing Origin/Referer header')
        host = request.host_url.rstrip('/')
        if not origin.startswith(host):
            abort(403, description='Cross-origin request rejected')
        return view(*args, **kwargs)
    return wrapped
