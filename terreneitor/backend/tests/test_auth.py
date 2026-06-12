"""
Tests de autenticación y autorización.
"""


def test_login_exitoso(test_client, test_user):
    """
    Test: Login con credenciales válidas debe retornar token JWT.
    """
    response = test_client.post(
        "/api/auth/login",
        json={"email": "test@terreneitor.com", "password": "password123"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data.get("ok") is True
    assert data.get("role") == "ADMIN"
    assert "access_token" in test_client.cookies


def test_login_email_incorrecto(test_client, test_user):
    """
    Test: Login con email incorrecto debe retornar 401.
    """
    response = test_client.post(
        "/api/auth/login",
        json={"email": "noexiste@terreneitor.com", "password": "password123"},
    )

    assert response.status_code == 401
    assert "detail" in response.json()


def test_login_password_incorrecta(test_client, test_user):
    """
    Test: Login con contraseña incorrecta debe retornar 401.
    """
    response = test_client.post(
        "/api/auth/login",
        json={"email": "test@terreneitor.com", "password": "wrongpassword"},
    )

    assert response.status_code == 401


def test_acceso_sin_token(test_client):
    """
    Test: Acceso a endpoint protegido sin token debe retornar 401.
    """
    response = test_client.get("/api/proyectos/")

    assert response.status_code == 401


def test_acceso_con_token_valido(test_client, auth_headers):
    """
    Test: Acceso a endpoint protegido con token válido debe funcionar.
    """
    response = test_client.get("/api/proyectos/", headers=auth_headers)

    # Puede retornar 200 (lista vacía) o 404 si no hay proyectos
    assert response.status_code in [200, 404]


def test_cambio_password(test_client, auth_headers, test_user):
    """
    Test: Cambio de contraseña debe funcionar correctamente.
    """
    response = test_client.post(
        "/api/auth/change-password",
        headers=auth_headers,
        json={
            "old_password": "password123",
            "new_password": "newpassword456",
        },
    )

    assert response.status_code == 200

    # Verificar que puede hacer login con la nueva contraseña
    login_response = test_client.post(
        "/api/auth/login",
        json={"email": "test@terreneitor.com", "password": "newpassword456"},
    )
    assert login_response.status_code == 200
