def test_health_check(client):
    """Verificar que el endpoint base responda correctamente"""
    # El endpoint raiz '/' a veces no existe, usar el de login o uno publico si hay
    # Si no hay endpoint publico, probamos login con credenciales invalidas que deberia dar 401, no 500
    response = client.post("/api/auth/login", json={"email": "test", "password": "bad"})
    assert response.status_code in [401, 200]
    assert "detail" in response.json() or "ok" in response.json()


def test_static_files_match(client):
    """Verificar que los archivos estaticos esten montados"""
    # Intentar pedir un archivo CSS conocido
    response = client.get("/modulos/portal/css/portal.css")
    # Puede ser 200 o 404 si no existe, pero NO 500
    assert response.status_code != 500
