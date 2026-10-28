from .desktop_service import download_claim_image
from .config import Settings

def save_image(image_url,root,day,person,number):
    return download_claim_image(Settings(download_path=str(root)),{'image':image_url,'date':day,'deadline':day,'folder':person,'number':number})
