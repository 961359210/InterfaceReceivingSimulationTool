# 接口接收模拟工具

一个使用 Python3 + Flask 构建的接口模拟服务：

- 支持自定义接口（路径 + 方法）、状态码、响应头、响应体、延迟
- 提供管理页面创建、删除、修改模拟接口
- 同时模拟多个接口（基于精确匹配）
- 可部署到 Linux 服务器并通过 IP:端口访问

## 开发运行（本地）

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
./.venv/bin/python run_servers.py  # 管理端口与模拟端口分离
```

访问（默认配置见 config.json）：

- 管理页面：`http://localhost:5174/admin/mocks`
- 模拟接口：`http://localhost:5175/<你配置的路径>`
- 健康检查（在管理端口上）：`http://localhost:5174/health`

## 使用说明

1. 在管理页面新建接口，填写：路径（如 `/api/test`）、方法（GET/POST/...）、状态码、`Content-Type`、响应头（JSON）、响应体（文本/JSON）、延迟（毫秒）和启用状态。
2. 保存后，发送同样方法与路径的请求，即返回所配置的响应。
3. 多个接口可以同时存在，按 “方法 + 路径” 精确匹配。

## 部署（Linux / 生产）

推荐使用 Gunicorn 启动两路服务（管理端 + 模拟端），并由 Nginx 做反向代理与可选的 HTTPS 终止：

1. 安装依赖：
   ```bash
   python3 -m venv .venv
   . .venv/bin/activate
   pip install -r requirements.txt
   ```
2. 配置端口与协议（修改 `config.json`）：
   ```json
   {
     "admin_protocol": "http",
     "admin_port": 5174,
     "mock_protocol": "http",
     "mock_port": 5175,
     "ssl_cert": null,
     "ssl_key": null
   }
   ```
3. 启动两路服务：
   ```bash
   # 管理服务（仅包含管理页面与健康检查）
   gunicorn -w 2 -b 0.0.0.0:5174 'app:create_app(include_admin=True, include_mock=False)'

   # 模拟服务（仅包含动态接口分发）
   gunicorn -w 2 -b 0.0.0.0:5175 'app:create_app(include_admin=False, include_mock=True)'
   ```
4. （可选）Nginx 反向代理示例：
   ```nginx
   server {
     listen 80;
     server_name example.com;

     location /admin/ {
       proxy_pass http://127.0.0.1:5174;
     }
     location /health {
       proxy_pass http://127.0.0.1:5174;
     }
     location / {
       proxy_pass http://127.0.0.1:5175;
     }
   }
   ```

如需直接以 HTTPS 运行（不经 Nginx），可提供有效证书与私钥并修改 `config.json`，再用 `./.venv/bin/python run_servers.py` 本地运行或通过 `gunicorn` 配合 `--keyfile/--certfile` 参数在各端口分别配置。

## 数据存储

- SQLite（`mocks.db`）用于运行时管理与查询。
- 接口定义会同步导出到 `mocks.json`（便于多环境部署与版本化）。
  - 包含：路径、方法、协议、状态码、`Content-Type`、响应头、响应体、启用、延迟（ms）。

## 打包（Linux/Windows）

为方便在 Linux 或 Windows 上分发为可执行文件，推荐使用 PyInstaller：

- 预备：
  - `python3 -m venv .venv && . .venv/bin/activate`
  - `pip install -r requirements.txt`
  - `pip install pyinstaller`

- 打包（macOS/Linux 命令）：
  - 单文件可执行（包含模板与默认配置）：
    ```bash
    pyinstaller --name InterfaceMockTool \
      --onefile \
      --add-data "templates:templates" \
      --add-data "config.json:." \
      run_servers.py
    ```
  - 生成产物：`dist/InterfaceMockTool`

- 打包（Windows 命令）：
  - 注意 `--add-data` 使用分号：
    ```powershell
    pyinstaller --name InterfaceMockTool `
      --onefile `
      --add-data "templates;templates" `
      --add-data "config.json;." `
      run_servers.py
    ```
  - 生成产物：`dist/InterfaceMockTool.exe`

- 运行与目录：
  - 可执行文件运行时默认使用工作目录中（或由环境变量）保存与读取数据：
    - 环境变量 `APP_DATA_DIR` 可指定数据目录（存放 `mocks.db`、`config.json`、`mocks.json`）。
    - 未设置时，默认使用可执行文件所在的当前工作目录。
  - 示例：
    ```bash
    # Linux/macOS
    APP_DATA_DIR=/opt/interface-mock ./InterfaceMockTool

    # Windows PowerShell
    $env:APP_DATA_DIR="C:\\interface-mock"; ./InterfaceMockTool.exe
    ```

- 端口与协议：
  - 按 `config.json` 的 `admin_port`/`mock_port` 与 `admin_protocol`/`mock_protocol` 启动两个端口。
  - 若配置为 `https`，需确保 `ssl_cert` 与 `ssl_key` 指向有效文件路径。

- 常见问题：
  - 如遇“模板未找到”，确保打包时包含 `templates` 目录（上面命令已包含）。
  - 如需修改默认配置，编辑同目录下的 `config.json` 或通过“系统设置”页面保存后重启。
  - 请在具备写权限的目录运行，以便创建/更新 `mocks.db` 与 `mocks.json`。

## 备份与迁移

- 直接拷贝 `mocks.db` 文件即可备份/迁移。