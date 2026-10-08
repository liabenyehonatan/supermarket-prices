# app/pipeline/shutdown.py
#
# Cooperative stop flag. The worker sets it on SIGTERM/SIGINT; long loops check
# it between files so a `docker stop` ends at a file boundary (every file is its
# own transaction) instead of being killed mid-load.

import threading

STOP = threading.Event()
