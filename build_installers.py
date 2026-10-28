"""Create native installation artifacts after build_desktop.py."""
import os,sys,shutil,subprocess
from pathlib import Path
root=Path(__file__).resolve().parent
source=root/(sys.argv[1] if len(sys.argv)>1 else 'dist')
output=root/'installers';output.mkdir(exist_ok=True)
if sys.platform=='win32':
    compiler=os.environ.get('ZB_ISCC') or shutil.which('ISCC.exe') or r'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
    if not Path(compiler).is_file():raise SystemExit('Install Inno Setup or set ZB_ISCC to ISCC.exe')
    subprocess.run([compiler,f'/DSourceDir={source / "ZBStudio"}',f'/DOutputDir={output}',str(root/'packaging/windows.iss')],check=True)
elif sys.platform=='darwin':
    import tempfile
    with tempfile.TemporaryDirectory(prefix='zb-dmg-') as temporary:
        staging=Path(temporary);shutil.copytree(source/'ZBStudio.app',staging/'ZB Studio.app',symlinks=True)
        (staging/'Applications').symlink_to('/Applications',target_is_directory=True)
        subprocess.run(['hdiutil','create','-volname','ZB Studio','-srcfolder',str(staging),'-ov','-format','UDZO',str(output/'ZBStudio-0.5.0-macOS.dmg')],check=True)
else:
    shutil.make_archive(str(output/'ZBStudio-0.5.0-Linux'),'gztar',root_dir=source)
