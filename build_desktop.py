"""Build from the project directory; bundle Python and Qt without a web server."""
import subprocess
import sys
from pathlib import Path
root=Path(__file__).resolve().parent
output=root/(sys.argv[1] if len(sys.argv)>1 else 'dist')
cmd=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--windowed','--name','ZBStudio','--paths','src','--collect-data','googleapiclient','--collect-data','certifi','--collect-all','keyring']
for package in ('PySide6','google-api-python-client','google-auth','google-auth-oauthlib','httpx','platformdirs','pydantic'):
    cmd.extend(['--copy-metadata',package])
cmd.extend(['--add-data',str(root/'zb_workflow_logo.svg')+':.'])
if sys.platform=='win32':
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QIcon
    app=QApplication.instance() or QApplication([])
    ico=root/'build'/'zb-workflow.ico';ico.parent.mkdir(exist_ok=True)
    if not QIcon(str(root/'zb_workflow_logo.svg')).pixmap(256,256).save(str(ico),'ICO'):raise RuntimeError('Logo conversion failed')
    cmd.extend(['--icon',str(ico)])
if sys.platform.startswith('linux'):cmd.extend(['--collect-all','secretstorage','--collect-all','jeepney'])
cmd.extend(['--distpath',str(output),'desktop_entry.py'])
subprocess.run(cmd,cwd=root,check=True)

# Qt on Windows uses the OS ICU API. PATH can contain a third-party ICU DLL
# with version-suffixed exports; bundling it shadows the system implementation.
if sys.platform == 'win32':
    conflicting=output/'ZBStudio'/'_internal'/'icuuc.dll'
    if conflicting.exists():
        import shutil
        diagnostics=root/'build'/'excluded-system-libraries'
        diagnostics.mkdir(parents=True,exist_ok=True)
        shutil.move(str(conflicting),str(diagnostics/'icuuc.dll'))
