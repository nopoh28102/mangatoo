# Gunicorn configuration for handling large file uploads
import os

# Server socket
bind = "0.0.0.0:5000"
backlog = 2048

# Worker processes
workers = 1
worker_class = "sync"
worker_connections = 1000
timeout = 300  # 5 minutes for large file uploads
keepalive = 2

# Restart workers after this many requests
max_requests = 1000
max_requests_jitter = 100

# Maximum size for request body (200MB)
limit_request_line = 8190
limit_request_fields = 100
limit_request_field_size = 16384

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "manga_platform"

# Auto reload for development
reload = True
reload_extra_files = ["routes.py", "main.py", "app/app.py"]

# Preload application for better performance
preload_app = False

# Enable reuse port for better performance
reuse_port = True