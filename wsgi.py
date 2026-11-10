"""WSGI-точка входа (PythonAnywhere, Apache mod_wsgi, gunicorn и др.).

Для PythonAnywhere в файле /var/www/<логин>_pythonanywhere_com_wsgi.py достаточно:

    import sys
    path = '/home/<логин>/vektor-events'
    if path not in sys.path:
        sys.path.insert(0, path)
    from wsgi import application
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app import app as application  # noqa: E402
