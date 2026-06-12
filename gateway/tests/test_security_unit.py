"""
Tests unitarios de gateway — funciones puras de seguridad/auth.

Sin DB ni docker. Cubren: detección de SECRET_KEY débil, hashing y
verificación de passwords, creación y verificación de JWT tokens.

Ejecutar:
    pytest gateway/tests/test_security_unit.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from plataforma.core import security


class TestPasswordHashing:
    """get_password_hash + verify_password — bcrypt round-trip."""

    def test_hash_no_es_password_plano(self):
        h = security.get_password_hash("mypassword123")
        assert h != "mypassword123"
        assert h.startswith("$2") or h.startswith("$pbkdf2") or h.startswith("$argon")

    def test_verify_password_correcto(self):
        h = security.get_password_hash("supersecret")
        assert security.verify_password("supersecret", h) is True

    def test_verify_password_incorrecto(self):
        h = security.get_password_hash("supersecret")
        assert security.verify_password("wrongpass", h) is False

    def test_hashes_son_distintos_aunque_password_sea_igual(self):
        # bcrypt usa salt distinto cada vez
        h1 = security.get_password_hash("samepass")
        h2 = security.get_password_hash("samepass")
        assert h1 != h2
        assert security.verify_password("samepass", h1) is True
        assert security.verify_password("samepass", h2) is True


class TestJWT:
    """create_access_token + verify_token — round-trip."""

    def test_token_round_trip_basico(self):
        token = security.create_access_token(subject="alice", role="admin")
        payload = security.verify_token(token)
        assert payload is not None
        assert payload["sub"] == "alice"
        assert payload["role"] == "admin"

    def test_token_invalido_devuelve_none(self):
        assert security.verify_token("not-a-real-token") is None
        assert security.verify_token("") is None
        assert security.verify_token("a.b.c") is None

    def test_token_normaliza_role_a_lowercase(self):
        token = security.create_access_token(subject="bob", role="ADMIN")
        payload = security.verify_token(token)
        assert payload["role"] == "admin"

    def test_token_incluye_roles_secundarios(self):
        token = security.create_access_token(
            subject="carol", role="admin",
            roles=["sistemas", "redes"],
        )
        payload = security.verify_token(token)
        assert "sistemas" in (payload.get("roles") or [])
        assert "redes" in (payload.get("roles") or [])

    def test_token_deduplica_roles(self):
        token = security.create_access_token(
            subject="dave", role="admin",
            roles=["sistemas", "SISTEMAS", "sistemas"],
        )
        payload = security.verify_token(token)
        roles = payload.get("roles") or []
        # Debería haber un solo "sistemas" (case insensitive + dedupe)
        assert roles.count("sistemas") == 1


class TestWeakSecret:
    """gateway._is_weak_secret — detección de claves inseguras."""

    def test_secret_vacio_es_debil(self):
        # Importamos desde gateway/main, que es donde está la función
        from gateway.backend import main as gw_main
        assert gw_main._is_weak_secret("") is True
        assert gw_main._is_weak_secret(None) is True

    def test_secret_corto_es_debil(self):
        from gateway.backend import main as gw_main
        assert gw_main._is_weak_secret("abc") is True
        assert gw_main._is_weak_secret("a" * 31) is True  # < 32 chars

    def test_secret_placeholder_es_debil(self):
        from gateway.backend import main as gw_main
        # Placeholders comunes deberían marcarse como débiles
        assert gw_main._is_weak_secret("replace_me") is True
        assert gw_main._is_weak_secret("changeme") is True
        assert gw_main._is_weak_secret("dev_only_change_me") is True

    def test_secret_robusto_no_es_debil(self):
        from gateway.backend import main as gw_main
        import secrets as _stdsecrets
        robust = _stdsecrets.token_urlsafe(64)
        assert gw_main._is_weak_secret(robust) is False
