"""Bounded HTTPS image fetches, including Drive shared-file URLs."""
import re
import socket
import ipaddress
from urllib.parse import urlparse,parse_qs
import httpx
LIMIT=8*1024*1024

def image_url(value):
    text=str(value or '').strip()
    match=re.match(r'=IMAGE\(\s*"([^"]+)"',text,re.I)
    return match[1] if match else text

def drive_id(value):
    u=urlparse(image_url(value))
    if u.hostname not in ('drive.google.com','docs.google.com'):return None
    match=re.search(r'/file/d/([\w-]+)',u.path)
    candidate=match[1] if match else parse_qs(u.query).get('id',[''])[0]
    return candidate if re.fullmatch(r'[\w-]+',candidate or '') else None

def public_bytes(url):
    # Pin the validated IP for each hop, but verify TLS against the original host.
    # Separate clients prevent cross-host connection reuse on shared IPs.
    for _ in range(6):
        u=urlparse(url)
        if u.scheme!='https' or not u.hostname or u.username or u.password:raise ValueError('图片地址必须是无用户名的 HTTPS')
        addresses=socket.getaddrinfo(u.hostname,u.port or 443,type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):raise ValueError('不允许访问内网图片地址')
        target=httpx.URL(url).copy_with(host=addresses[0][4][0])
        with httpx.Client(timeout=20,follow_redirects=False,trust_env=False) as client:
            with client.stream('GET',target,headers={'Host':httpx.URL(url).netloc.decode(),'Accept-Encoding':'identity'},extensions={'sni_hostname':u.hostname}) as response:
                if response.is_redirect:
                    from urllib.parse import urljoin
                    url=urljoin(url,response.headers['location']);continue
                response.raise_for_status()
                if not response.headers.get('content-type','').lower().startswith('image/'):raise ValueError('链接返回的不是图片')
                data=bytearray()
                for chunk in response.iter_bytes(chunk_size=65536):
                    if len(data)+len(chunk)>LIMIT:raise ValueError('图片超过 8 MB')
                    data.extend(chunk)
                return bytes(data)
    raise ValueError('图片重定向次数过多')


def fetch_image(value,original=False):
    url=image_url(value);fid=drive_id(url)
    if not url:raise ValueError('图片链接为空')
    if not fid:return public_bytes(url)
    try:return public_bytes(('https://drive.google.com/uc?export=download&id='+fid) if original else ('https://drive.google.com/thumbnail?id='+fid+'&sz=w640'))
    except Exception:
        from google.auth.transport.requests import AuthorizedSession
        from .google_client import credentials
        try:
            with AuthorizedSession(credentials()) as session:
                with session.get('https://www.googleapis.com/drive/v3/files/'+fid,params={'alt':'media'},stream=True,timeout=25) as response:
                    response.raise_for_status()
                    if not response.headers.get('content-type','').startswith('image/'):raise ValueError('Drive 文件不是图片')
                    data=bytearray()
                    for chunk in response.iter_content(65536):
                        data.extend(chunk)
                        if len(data)>LIMIT:raise ValueError('图片超过预览大小限制')
                    return bytes(data)
        except Exception as e:raise ValueError('Drive 图片读取失败，请检查文件共享权限及当前 Google 账号访问权限') from e
