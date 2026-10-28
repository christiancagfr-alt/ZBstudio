"""Only OS-backed credential stores; never use plaintext fallback backends."""
import sys
import json

SERVICE='ZB Studio'
ACCOUNT='google-oauth-token'


def backend():
    try:
        if sys.platform=='win32':
            from keyring.backends.Windows import WinVaultKeyring
            store=WinVaultKeyring()
        elif sys.platform=='darwin':
            from keyring.backends.macOS import Keyring
            store=Keyring()
        else:
            from keyring.backends.SecretService import Keyring
            store=Keyring()
        if store.priority<=0:raise RuntimeError()
        return store
    except Exception as e:raise ValueError('系统凭据库不可用。Linux 请启用并解锁 Secret Service；不会保存明文登录凭据。') from e


def save(raw):
    store=backend()
    try:
        store.set_password(SERVICE,ACCOUNT,raw)
        if store.get_password(SERVICE,ACCOUNT)!=raw:raise RuntimeError('credential verification failed')
    except Exception as e:raise ValueError('无法保存登录到系统凭据库，请检查凭据库是否已解锁') from e


def load(legacy):
    try:raw=backend().get_password(SERVICE,ACCOUNT)
    except Exception as e:raise ValueError('无法读取系统凭据库，请解锁后重试') from e
    if legacy.exists():
        previous=legacy.read_text('utf-8');json.loads(previous)
        if raw is None:save(previous);raw=previous
        # A successful vault read/write precedes removal; failure retains legacy.
        legacy.unlink()
    return raw


def clear(legacy):
    from keyring.errors import PasswordDeleteError
    try:backend().delete_password(SERVICE,ACCOUNT)
    except PasswordDeleteError:pass
    legacy.unlink(missing_ok=True)
