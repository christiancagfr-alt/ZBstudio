"""Create native installation artifacts after build_desktop.py."""
import os,sys,shutil,subprocess
import hashlib
from pathlib import Path
root=Path(__file__).resolve().parent
sys.path.insert(0,str(root/'src'))
from zb_studio.version import APP_VERSION
from zb_studio.package_safety import assert_safe_release_tree
source=root/(sys.argv[1] if len(sys.argv)>1 else 'dist')
output=root/'installers';output.mkdir(exist_ok=True)
assert_safe_release_tree(source)
if sys.platform=='win32':
    compiler=os.environ.get('ZB_ISCC') or shutil.which('ISCC.exe') or r'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
    if not Path(compiler).is_file():raise SystemExit('Install Inno Setup or set ZB_ISCC to ISCC.exe')
    subprocess.run([compiler,f'/DSourceDir={source / "ZBStudio"}',f'/DOutputDir={output}',f'/DAppVersion={APP_VERSION}',str(root/'packaging/windows.iss')],check=True)
elif sys.platform=='darwin':
    import tempfile
    with tempfile.TemporaryDirectory(prefix='zb-dmg-') as temporary:
        staging=Path(temporary);shutil.copytree(source/'ZBStudio.app',staging/'ZB Studio.app',symlinks=True)
        (staging/'Applications').symlink_to('/Applications',target_is_directory=True)
        subprocess.run(['hdiutil','create','-volname','ZB Studio','-srcfolder',str(staging),'-ov','-format','UDZO',str(output/f'ZBStudio-{APP_VERSION}-macOS.dmg')],check=True)
else:
    shutil.make_archive(str(output/f'ZBStudio-{APP_VERSION}-Linux'),'gztar',root_dir=source)

artifacts=sorted(path for path in output.iterdir() if path.is_file() and path.name.startswith(f'ZBStudio-{APP_VERSION}-') and not path.name.endswith('SHA256SUMS.txt'))
manifest=output/f'ZBStudio-{APP_VERSION}-SHA256SUMS.txt'
def sha256(path):
    hasher=hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda:source.read(1024*1024),b''):hasher.update(block)
    return hasher.hexdigest()
manifest.write_text(''.join(f'{sha256(path)}  {path.name}\n' for path in artifacts),'utf-8')
print(f'Created {manifest.name} for {len(artifacts)} release artifact(s)')
