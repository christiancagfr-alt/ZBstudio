"""Request limits run before multipart parsing, including chunked bodies."""
from starlette.responses import JSONResponse

class BodyLimitMiddleware:
    def __init__(self,app):self.app=app
    async def __call__(self,scope,receive,send):
        if scope['type']!='http':return await self.app(scope,receive,send)
        limit=8*1024**3 if scope.get('path')=='/api/uploads/video' else 1024*1024
        headers=dict(scope.get('headers',[]))
        try:length=int(headers.get(b'content-length',b'0'))
        except ValueError:length=-1
        if length<0 or length>limit:
            return await JSONResponse({'detail':'请求体过大或长度无效'},status_code=413)(scope,receive,send)
        received=0;started=False
        class TooLarge(Exception):pass
        async def bounded_receive():
            nonlocal received
            message=await receive()
            if message['type']=='http.request':
                received+=len(message.get('body',b''))
                if received>limit:raise TooLarge()
            return message
        async def track_send(message):
            nonlocal started
            if message['type']=='http.response.start':started=True
            await send(message)
        try:await self.app(scope,bounded_receive,track_send)
        except TooLarge:
            if not started:await JSONResponse({'detail':'请求体超过大小限制'},status_code=413)(scope,receive,send)
