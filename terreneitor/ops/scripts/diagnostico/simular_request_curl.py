import argparse
import datetime
import os

import jwt
import requests

SECRET_KEY = os.environ.get("TERRENEITOR_SECRET_KEY")
ALGORITHM = "HS256"
DEFAULT_BASE_URL = os.environ.get("TERRENEITOR_BASE_URL", "http://localhost:8005")


def create_token(email: str, role: str) -> str:
    if not SECRET_KEY:
        raise SystemExit("TERRENEITOR_SECRET_KEY no esta definido en el entorno.")
    expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=30)
    to_encode = {"sub": email, "role": role, "exp": expire}
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def run(path: str, base_url: str, email: str, role: str) -> None:
    url = f"{base_url}{path}"
    token = create_token(email, role)
    headers = {"Authorization": f"Bearer {token}"}
    print(f"Requesting {url}...")
    resp = requests.get(url, headers=headers)
    print(f"Status Code: {resp.status_code}")
    print("Response Body:")
    print(resp.text)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Simula un request autenticado a la API."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default="/api/asignacion/280/archivos-por-validar",
        help="Path de la API (con / inicial). Default: ejemplo de validacion.",
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--email", default="juan.lopez@telconsulting.cl")
    parser.add_argument("--role", default="ADMIN")
    args = parser.parse_args()
    run(args.path, args.base_url, args.email, args.role)
