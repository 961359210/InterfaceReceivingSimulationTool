import json
import os
import sqlite3
import sys
import logging
from flask import Flask, request, jsonify, g, render_template, redirect, url_for, flash, Blueprint, make_response


BASE_DIR = os.environ.get('APP_DATA_DIR') or os.path.dirname(__file__)

def resource_path(rel_path: str) -> str:
    base = getattr(sys, '_MEIPASS', os.path.dirname(__file__))
    return os.path.join(base, rel_path)

DATABASE = os.path.join(BASE_DIR, 'mocks.db')
CONFIG_PATH = os.path.join(BASE_DIR, 'config.json')
MOCKS_JSON_PATH = os.path.join(BASE_DIR, 'mocks.json')


def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS mocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL,
            method TEXT NOT NULL,
            scheme TEXT NOT NULL DEFAULT 'http',
            status_code INTEGER NOT NULL DEFAULT 200,
            content_type TEXT NOT NULL DEFAULT 'application/json',
            headers_json TEXT NOT NULL DEFAULT '{}',
            body TEXT NOT NULL DEFAULT '',
            enabled INTEGER NOT NULL DEFAULT 1,
            delay_ms INTEGER NOT NULL DEFAULT 0,
            UNIQUE(path, method)
        );
        """
    )
    db.commit()
    # Ensure schema compatibility for existing databases
    try:
        cols = db.execute("PRAGMA table_info(mocks)").fetchall()
        col_names = {c[1] for c in cols}
        if 'scheme' not in col_names:
            db.execute("ALTER TABLE mocks ADD COLUMN scheme TEXT NOT NULL DEFAULT 'http'")
            db.commit()
    except Exception:
        pass


def create_app(include_admin: bool = True, include_mock: bool = True):
    app = Flask(__name__, template_folder=resource_path('templates'))
    app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret')
    # 初始化结构化日志，仅添加一次 handler 避免重复
    logger = logging.getLogger('mock_service')
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    @app.before_request
    def before_request():
        get_db()

    @app.teardown_appcontext
    def teardown_db(exception):
        close_db()

    with app.app_context():
        init_db()

    def export_mocks_to_file():
        db = get_db()
        rows = db.execute('SELECT * FROM mocks ORDER BY path, method').fetchall()
        data = []
        for r in rows:
            try:
                headers_obj = json.loads(r['headers_json'] or '{}')
            except Exception:
                headers_obj = {}
            data.append({
                'id': r['id'],
                'path': r['path'],
                'method': r['method'],
                'scheme': r['scheme'],
                'status_code': int(r['status_code']),
                'content_type': r['content_type'],
                'headers': headers_obj,
                'body': r['body'],
                'enabled': bool(r['enabled']),
                'delay_ms': int(r['delay_ms']),
            })
        try:
            with open(MOCKS_JSON_PATH, 'w', encoding='utf-8') as f:
                json.dump({'mocks': data}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    if include_admin:
        admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

        @admin_bp.route('/')
        def index():
            return redirect(url_for('admin.list_mocks'))

        @admin_bp.route('/mocks')
        def list_mocks():
            db = get_db()
            rows = db.execute('SELECT * FROM mocks ORDER BY path, method').fetchall()
            return render_template('mocks_list.html', mocks=rows)

        @admin_bp.route('/mocks/new', methods=['GET'])
        def new_mock():
            return render_template('mock_form.html', mock=None)

        @admin_bp.route('/mocks', methods=['POST'])
        def create_mock():
            db = get_db()
            path = request.form.get('path', '').strip()
            method = request.form.get('method', 'GET').strip().upper()
            scheme = request.form.get('scheme', 'http').strip().lower()
            status_code = int(request.form.get('status_code', '200'))
            content_type = request.form.get('content_type', 'application/json').strip()
            headers_raw = request.form.get('headers_json', '{}').strip() or '{}'
            body = request.form.get('body', '')
            enabled = 1 if request.form.get('enabled') == 'on' else 0
            delay_ms = int(request.form.get('delay_ms', '0') or '0')

            # Validate headers JSON
            try:
                json.loads(headers_raw or '{}')
            except Exception:
                flash('Headers JSON 格式错误', 'danger')
                return render_template('mock_form.html', mock=None, form_error='headers_json')

            try:
                db.execute(
                    'INSERT INTO mocks (path, method, scheme, status_code, content_type, headers_json, body, enabled, delay_ms)\n                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                    (path, method, scheme, status_code, content_type, headers_raw, body, enabled, delay_ms)
                )
                db.commit()
                export_mocks_to_file()
                flash('Mock 接口已创建', 'success')
            except sqlite3.IntegrityError:
                flash('同一路径与方法已存在，请修改', 'warning')
                return render_template('mock_form.html', mock=None)

            return redirect(url_for('admin.list_mocks'))

        @admin_bp.route('/mocks/<int:mock_id>/edit', methods=['GET'])
        def edit_mock(mock_id):
            db = get_db()
            row = db.execute('SELECT * FROM mocks WHERE id = ?', (mock_id,)).fetchone()
            if not row:
                flash('未找到接口', 'warning')
                return redirect(url_for('admin.list_mocks'))
            return render_template('mock_form.html', mock=row)

        @admin_bp.route('/mocks/<int:mock_id>/update', methods=['POST'])
        def update_mock(mock_id):
            db = get_db()
            path = request.form.get('path', '').strip()
            method = request.form.get('method', 'GET').strip().upper()
            scheme = request.form.get('scheme', 'http').strip().lower()
            status_code = int(request.form.get('status_code', '200'))
            content_type = request.form.get('content_type', 'application/json').strip()
            headers_raw = request.form.get('headers_json', '{}').strip() or '{}'
            body = request.form.get('body', '')
            enabled = 1 if request.form.get('enabled') == 'on' else 0
            delay_ms = int(request.form.get('delay_ms', '0') or '0')

            try:
                json.loads(headers_raw or '{}')
            except Exception:
                flash('Headers JSON 格式错误', 'danger')
                row = db.execute('SELECT * FROM mocks WHERE id = ?', (mock_id,)).fetchone()
                return render_template('mock_form.html', mock=row, form_error='headers_json')

            try:
                db.execute(
                    'UPDATE mocks SET path = ?, method = ?, scheme = ?, status_code = ?, content_type = ?, headers_json = ?, body = ?, enabled = ?, delay_ms = ? WHERE id = ?',
                    (path, method, scheme, status_code, content_type, headers_raw, body, enabled, delay_ms, mock_id)
                )
                db.commit()
                export_mocks_to_file()
                flash('Mock 接口已更新', 'success')
            except sqlite3.IntegrityError:
                flash('同一路径与方法已存在，请修改', 'warning')
                row = db.execute('SELECT * FROM mocks WHERE id = ?', (mock_id,)).fetchone()
                return render_template('mock_form.html', mock=row)

            return redirect(url_for('admin.list_mocks'))

        @admin_bp.route('/mocks/<int:mock_id>/delete', methods=['POST'])
        def delete_mock(mock_id):
            db = get_db()
            db.execute('DELETE FROM mocks WHERE id = ?', (mock_id,))
            db.commit()
            export_mocks_to_file()
            flash('Mock 接口已删除', 'success')
            return redirect(url_for('admin.list_mocks'))

        @admin_bp.route('/settings', methods=['GET', 'POST'])
        def settings():
            cfg = load_config()
            if request.method == 'POST':
                try:
                    admin_protocol = request.form.get('admin_protocol', 'http').strip().lower()
                    mock_protocol = request.form.get('mock_protocol', 'http').strip().lower()
                    admin_port = int(request.form.get('admin_port', cfg.get('admin_port', 5174)))
                    mock_port = int(request.form.get('mock_port', cfg.get('mock_port', 5175)))
                    ssl_cert = request.form.get('ssl_cert') or None
                    ssl_key = request.form.get('ssl_key') or None
                    new_cfg = {
                        'admin_protocol': admin_protocol,
                        'admin_port': admin_port,
                        'mock_protocol': mock_protocol,
                        'mock_port': mock_port,
                        'ssl_cert': ssl_cert,
                        'ssl_key': ssl_key,
                    }
                    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                        json.dump(new_cfg, f, ensure_ascii=False, indent=2)
                    flash('配置已保存（重启服务后生效）', 'success')
                    cfg = new_cfg
                except Exception:
                    flash('配置保存失败', 'danger')
            return render_template('settings.html', cfg=cfg)

        app.register_blueprint(admin_bp)

    # Health check
    @app.get('/health')
    def health():
        return jsonify({'status': 'ok'})

    if include_mock:
        # Catch-all dispatcher for dynamic mocks
        @app.route('/', defaults={'req_path': ''}, methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'])
        @app.route('/<path:req_path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'])
        def mock_dispatch(req_path):
            # Do not capture admin routes
            if request.path.startswith('/admin'):
                logging.getLogger('mock_service').warning(
                    f"[404] Admin path blocked: {request.method} {request.path}"
                )
                return 'Not Found', 404

            db = get_db()
            cur_scheme = getattr(request, 'scheme', 'http') or 'http'
            # 记录请求关键信息
            try:
                qs = request.query_string.decode('utf-8', 'ignore')
            except Exception:
                qs = ''
            body_preview = ''
            if request.method in ('POST', 'PUT', 'PATCH'):
                try:
                    body_preview = request.get_data(as_text=True)[:1000]
                except Exception:
                    body_preview = '<unavailable>'
            logging.getLogger('mock_service').info(
                f"[REQ] {request.method} {request.path} scheme={cur_scheme} qs='{qs}' ip={request.remote_addr} "
                f"ctype={request.headers.get('Content-Type')} ua={request.headers.get('User-Agent')} body_len={len(body_preview)}"
            )
            row = db.execute(
                'SELECT * FROM mocks WHERE path = ? AND method = ? AND scheme = ? AND enabled = 1',
                (f'/{req_path}', request.method, cur_scheme)
            ).fetchone()

            if not row:
                # 细化404原因并打印日志
                rows_for_path = db.execute(
                    'SELECT method, scheme, enabled FROM mocks WHERE path = ?', (f'/{req_path}',)
                ).fetchall()
                if not rows_for_path:
                    reason = '路径未配置'
                elif not any(r['method'] == request.method for r in rows_for_path):
                    reason = '方法未配置'
                elif not any(r['method'] == request.method and r['scheme'] == cur_scheme for r in rows_for_path):
                    reason = '协议不匹配'
                elif not any(r['method'] == request.method and r['scheme'] == cur_scheme and r['enabled'] == 1 for r in rows_for_path):
                    reason = '接口已禁用'
                else:
                    reason = '未匹配的其他原因'
                logging.getLogger('mock_service').warning(
                    f"[404] {request.method} {request.path} reason={reason} scheme={cur_scheme}"
                )
                return 'Mock 未配置', 404

            # Optional delay
            delay_ms = int(row['delay_ms'] or 0)
            if delay_ms > 0:
                import time
                time.sleep(delay_ms / 1000.0)

            status_code = int(row['status_code'])
            content_type = row['content_type'] or 'application/json'

            # Prepare response body
            body_text = row['body'] or ''

            # Set headers
            headers = {}
            try:
                headers = json.loads(row['headers_json'] or '{}')
            except Exception:
                headers = {}
                logging.getLogger('mock_service').warning(
                    f"Invalid headers_json for mock id={row['id']} path={row['path']}"
                )

            resp = make_response(body_text, status_code)
            resp.headers['Content-Type'] = content_type
            for k, v in headers.items():
                resp.headers[k] = v
            logging.getLogger('mock_service').info(
                f"[RESP] {request.method} {request.path} -> {status_code} ctype={content_type} headers={len(headers)} "
                f"body_len={len(body_text or '')} delay_ms={delay_ms}"
            )
            return resp

    return app


def load_config():
    cfg = {
        'admin_protocol': 'http',
        'admin_port': 5174,
        'mock_protocol': 'http',
        'mock_port': 5175,
        'ssl_cert': None,
        'ssl_key': None,
    }
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                file_cfg = json.load(f)
                cfg.update({k: v for k, v in file_cfg.items() if v is not None})
    except Exception:
        pass
    return cfg


app = create_app()

if __name__ == '__main__':
    # 单应用运行（开发便捷），读取 admin_port
    cfg = load_config()
    app.run(host='0.0.0.0', port=int(cfg.get('admin_port', 5174)), debug=True)