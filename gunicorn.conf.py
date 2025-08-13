# Gunicorn configuration file
# Optimized for manga platform with large ZIP uploads

# Server socket
bind = "0.0.0.0:5000"
workers = 2
worker_class = "sync"

# Timeout settings (important for large file uploads)
timeout = 300  # 5 minutes for worker timeout
keepalive = 2
max_requests = 1000
max_requests_jitter = 50

# File upload limits and buffer sizes
limit_request_line = 8192
limit_request_fields = 100
limit_request_field_size = 16384

# Process naming
proc_name = "manga_platform"

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process management
preload_app = False
reload = True  # Development mode
capture_output = True
enable_stdio_inheritance = True

# Security
forwarded_allow_ips = "*"
secure_headers = True