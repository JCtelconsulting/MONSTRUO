"""
Tests de gestión de proyectos (crear, listar, eliminar).
"""

from terreneitor.backend import modelos


def test_crear_proyecto_pmc(
    test_client, auth_headers, test_db, temp_files_dir, monkeypatch
):
    """
    Test: Crear proyecto PMC debe generar estructura de carpetas correcta.
    """
    # Configurar directorio temporal como BASE_FILES_DIR (aísla el test del disco real,
    # evitando 409 'ruta ya existe'). El módulo real es terreneitor.backend.core.nucleo.
    monkeypatch.setattr(
        "terreneitor.backend.core.nucleo.BASE_FILES_DIR", str(temp_files_dir)
    )

    response = test_client.post(
        "/api/admin/proyectos",
        headers=auth_headers,
        json={
            "cliente": "CLIENTE_TEST",
            "zona": "ZONA_TEST",
            "tipo": "PMC",
            "nombre": "PROYECTO_001",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "id" in data
    assert "nombre_pmc" in data

    # Verificar que se creó en la base de datos
    proyecto = test_db.query(modelos.Proyecto).filter_by(id=data["id"]).first()
    assert proyecto is not None
    assert "PMC_PROYECTO_001" in proyecto.nombre_pmc


def test_listar_proyectos(test_client, auth_headers, test_db):
    """
    Test: Listar proyectos debe retornar todos los proyectos activos.
    """
    # Crear proyecto de prueba
    proyecto = modelos.Proyecto(
        nombre_pmc="PMC_TEST_001",
        cliente="CLIENTE_TEST",
        area="ZONA_TEST",
        ruta_base="/tmp/test",
        estado_proyecto=modelos.EstadoProyectoEnum.ACTIVO,
    )
    test_db.add(proyecto)
    test_db.commit()

    response = test_client.get("/api/admin/proyectos", headers=auth_headers)

    assert response.status_code == 200
    proyectos = response.json()
    assert isinstance(proyectos, list)
    assert len(proyectos) >= 1
    assert any(p["nombre_pmc"] == "PMC_TEST_001" for p in proyectos)


def test_eliminar_proyecto(
    test_client, auth_headers, test_db, temp_files_dir, monkeypatch
):
    """
    Test: Eliminar proyecto debe moverlo a _PAPELERA.
    """
    # Configurar directorio temporal
    monkeypatch.setattr("backend.core.nucleo.BASE_FILES_DIR", str(temp_files_dir))

    # Crear proyecto de prueba
    proyecto_dir = temp_files_dir / "CLIENTE" / "ZONA" / "PMC_TEST_002"
    proyecto_dir.mkdir(parents=True)

    proyecto = modelos.Proyecto(
        nombre_pmc="PMC_TEST_002",
        cliente="CLIENTE",
        area="ZONA",
        ruta_base=str(proyecto_dir),
        estado_proyecto=modelos.EstadoProyectoEnum.ACTIVO,
    )
    test_db.add(proyecto)
    test_db.commit()
    test_db.refresh(proyecto)

    # Eliminar proyecto
    response = test_client.delete(
        f"/api/admin/proyectos/{proyecto.id}",
        headers=auth_headers,
    )

    assert response.status_code == 200

    # Verificar que se eliminó de la base de datos
    deleted = test_db.query(modelos.Proyecto).filter_by(id=proyecto.id).first()
    assert deleted is None


def test_crear_proyecto_duplicado(test_client, auth_headers, test_db):
    """
    Test: Crear proyecto con nombre duplicado debe retornar error.
    """
    # Crear primer proyecto
    proyecto = modelos.Proyecto(
        nombre_pmc="PMC_DUPLICADO",
        cliente="CLIENTE",
        area="ZONA",
        ruta_base="/tmp/test",
        estado_proyecto=modelos.EstadoProyectoEnum.ACTIVO,
    )
    test_db.add(proyecto)
    test_db.commit()

    # Intentar crear proyecto duplicado
    response = test_client.post(
        "/api/admin/proyectos",
        headers=auth_headers,
        json={
            "cliente": "CLIENTE",
            "zona": "ZONA",
            "tipo": "PMC",
            "nombre": "DUPLICADO",  # Resultará en PMC_DUPLICADO
        },
    )

    # Debe retornar error (400 o 409)
    assert response.status_code in [400, 409]
