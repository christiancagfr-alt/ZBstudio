import hashlib
from pathlib import Path

import pytest

from zb_studio import updater


def test_version_and_platform_asset_selection():
    assert updater.version_key('v0.5.10') > updater.version_key('0.5.9')
    assert updater.platform_asset_suffix('win32') == 'Windows-Setup.exe'
    assert updater.platform_asset_suffix('darwin') == 'macOS.dmg'
    assert updater.platform_asset_suffix('linux') == 'Linux.tar.gz'
    with pytest.raises(ValueError):
        updater.version_key('latest')


def test_checksum_manifest_and_verification(tmp_path):
    package=tmp_path/'ZBStudio-0.5.2-Windows-Setup.exe';package.write_bytes(b'installer')
    digest=hashlib.sha256(b'installer').hexdigest()
    manifest=tmp_path/'ZBStudio-0.5.2-SHA256SUMS.txt';manifest.write_text(f'{digest}  {package.name}\n','utf-8')
    assert updater._expected_digest(manifest,package.name)==digest
    updater._verify(package,digest)
    with pytest.raises(ValueError):updater._verify(package,'0'*64)
    assert not package.exists()


def test_safe_linux_extraction_rejects_escape_and_links(tmp_path):
    import tarfile
    bad=tmp_path/'bad.tar.gz'
    with tarfile.open(bad,'w:gz') as archive:
        info=tarfile.TarInfo('../escape');info.size=0;archive.addfile(info)
    with pytest.raises(ValueError):updater._safe_extract(bad,tmp_path/'out')


def test_release_tree_rejects_local_configuration(tmp_path):
    from zb_studio.package_safety import assert_safe_release_tree
    (tmp_path/'settings.json').write_text('{}','utf-8')
    with pytest.raises(RuntimeError,match='settings.json'):assert_safe_release_tree(tmp_path)


def test_release_tree_allows_google_discovery_schemas(tmp_path):
    from zb_studio.package_safety import assert_safe_release_tree
    schema=tmp_path/'_internal'/'googleapiclient'/'discovery_cache'/'documents'/'iamcredentials.v1.json'
    schema.parent.mkdir(parents=True);schema.write_text('{}','utf-8')
    assert_safe_release_tree(tmp_path)


def test_first_launch_has_no_personal_producer_preset():
    from zb_studio.config import Settings
    assert Settings().producer == ''
