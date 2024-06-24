# auth_utils.py
from jose import jwt
from fastapi import Security, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose.exceptions import JWTError
import os

# Environment variables for Auth0
AUTH0_DOMAIN = os.getenv("AUTH0_DOMAIN")
API_AUDIENCE = os.getenv("API_AUDIENCE")
ALGORITHMS = ["RS256"]

if not AUTH0_DOMAIN or not API_AUDIENCE:
    raise ValueError("Auth0 domain and API audience must be set")

class Auth0:
    def __init__(self):
        self.domain = AUTH0_DOMAIN
        self.audience = API_AUDIENCE
        self.algorithms = ALGORITHMS

    def get_jwks(self):
        from urllib.request import urlopen
        import json

        jwks_url = f"https://{self.domain}/.well-known/jwks.json"
        response = urlopen(jwks_url)
        return json.loads(response.read())

    def decode_jwt(self, token: str):
        jwks = self.get_jwks()
        unverified_header = jwt.get_unverified_header(token)

        rsa_key = {}
        for key in jwks["keys"]:
            if key["kid"] == unverified_header["kid"]:
                rsa_key = {
                    "kty": key["kty"],
                    "kid": key["kid"],
                    "use": key["use"],
                    "n": key["n"],
                    "e": key["e"]
                }
        
        if rsa_key:
            try:
                payload = jwt.decode(
                    token,
                    rsa_key,
                    algorithms=self.algorithms,
                    audience=self.audience,
                    issuer=f"https://{self.domain}/"
                )
                return payload
            except JWTError:
                raise HTTPException(status_code=401, detail="Could not validate credentials")
        raise HTTPException(status_code=401, detail="Could not validate credentials")

auth0 = Auth0()
security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security)):
    token = credentials.credentials
    payload = auth0.decode_jwt(token)
    return payload
