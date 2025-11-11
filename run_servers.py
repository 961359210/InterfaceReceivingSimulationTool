import os
import json
import threading
from werkzeug.serving import run_simple

from app import create_app, load_config


def run_admin(cfg):
    app = create_app(include_admin=True, include_mock=False)
    use_https = str(cfg.get('admin_protocol', 'http')).lower() == 'https'
    ssl_ctx = None
    if use_https:
        cert = cfg.get('ssl_cert')
        key = cfg.get('ssl_key')
        if cert and key and os.path.exists(cert) and os.path.exists(key):
            ssl_ctx = (cert, key)
    run_simple('0.0.0.0', int(cfg.get('admin_port', 5174)), app, use_reloader=False, ssl_context=ssl_ctx)


def run_mock(cfg):
    app = create_app(include_admin=False, include_mock=True)
    use_https = str(cfg.get('mock_protocol', 'http')).lower() == 'https'
    ssl_ctx = None
    if use_https:
        cert = cfg.get('ssl_cert')
        key = cfg.get('ssl_key')
        if cert and key and os.path.exists(cert) and os.path.exists(key):
            ssl_ctx = (cert, key)
    run_simple('0.0.0.0', int(cfg.get('mock_port', 5175)), app, use_reloader=False, ssl_context=ssl_ctx)


if __name__ == '__main__':
    cfg = load_config()
    t1 = threading.Thread(target=run_admin, args=(cfg,), daemon=True)
    t2 = threading.Thread(target=run_mock, args=(cfg,), daemon=True)
    t1.start()
    t2.start()
    # Join to keep main thread alive
    t1.join()
    t2.join()