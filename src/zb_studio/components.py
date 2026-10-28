"""Read-only runtime diagnosis. Bundled components update with the application."""
import importlib.metadata
import platform
import sys
PACKAGES=('PySide6','google-api-python-client','google-auth','google-auth-oauthlib','httpx','platformdirs','pydantic')
def inspect_components():
    rows=[('系统',platform.platform(),'正常'),('Python',platform.python_version(),'随软件打包' if getattr(sys,'frozen',False) else '开发环境')]
    for name in PACKAGES:
        try:rows.append((name,importlib.metadata.version(name),'正常'))
        except importlib.metadata.PackageNotFoundError:rows.append((name,'未检测到','需要修复安装包' if getattr(sys,'frozen',False) else '缺少开发依赖'))
    return rows
