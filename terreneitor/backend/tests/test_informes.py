"""
Tests de generación de informes PDF.
"""

from datetime import datetime

from backend import modelos


def test_generar_informe_basico(test_client, auth_headers, test_db):
    """
    Test: POST /api/reportes/generar arranca un job async y devuelve job_id.
    El endpoint NO retorna el archivo directamente; el cliente despues
    consulta /api/informes/job-status/{job_id} hasta que complete.
    """
    proyecto = modelos.Proyecto(
        nombre_pmc="PMC_INFORME",
        cliente="CLIENTE_INFORME",
        area="ZONA_INFORME",
        ruta_base="/tmp/test_informe",
        estado_proyecto=modelos.EstadoProyectoEnum.ACTIVO,
    )
    test_db.add(proyecto)
    test_db.commit()

    response = test_client.post(
        "/api/reportes/generar",
        headers=auth_headers,
        json={
            "tipo": "diario",
            "fecha_inicio": datetime.now().date().isoformat(),
            "proyectos_ids": [proyecto.id],
        },
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert "job_id" in data
    assert isinstance(data["job_id"], str) and len(data["job_id"]) > 0


def test_generar_informe_sin_fotos(test_client, auth_headers, test_db):
    """
    Test: Generar informe sin fotos debe retornar error o PDF vacío.
    """
    # Crear proyecto vacío
    proyecto = modelos.Proyecto(
        nombre_pmc="PMC_VACIO",
        cliente="CLIENTE",
        area="ZONA",
        ruta_base="/tmp/test_vacio",
        estado_proyecto=modelos.EstadoProyectoEnum.ACTIVO,
    )
    test_db.add(proyecto)
    test_db.commit()

    # Intentar generar informe
    response = test_client.post(
        "/api/reportes/generar",
        headers=auth_headers,
        json={
            "tipo": "diario",
            "fecha_inicio": datetime.now().date().isoformat(),
            "proyectos_ids": [proyecto.id],
        },
    )

    # Debe retornar error o PDF vacío
    assert response.status_code in [200, 400, 404]
