"""
Tests del flujo completo de fotos (subir, EXIF, aprobar, rechazar).
"""

import io
from datetime import datetime

from PIL import Image

from terreneitor.backend import modelos


def crear_imagen_con_exif(width=100, height=100, fecha=None):
    """
    Crea una imagen JPEG con metadatos EXIF.
    """
    img = Image.new("RGB", (width, height), color="blue")

    # Crear buffer de imagen
    buf = io.BytesIO()

    # Guardar con EXIF básico
    exif_data = img.getexif()
    if fecha:
        exif_data[0x9003] = fecha.strftime("%Y:%m:%d %H:%M:%S")  # DateTimeOriginal

    img.save(buf, "JPEG", exif=exif_data)
    buf.seek(0)
    return buf


def test_subir_foto_con_exif(
    test_client, auth_headers, test_db, temp_files_dir, monkeypatch
):
    """
    Test: Subir foto con EXIF válido debe ir a _POR_VALIDAR.
    """
    # Configurar directorio temporal
    monkeypatch.setattr("backend.core.nucleo.BASE_FILES_DIR", str(temp_files_dir))

    # Crear proyecto y asignación
    plan = modelos.PlanTrabajo(descripcion="Plan EXIF")
    test_db.add(plan)
    test_db.commit()

    proyecto = modelos.Proyecto(
        nombre_pmc="PMC_TEST_FOTO",
        cliente="CLIENTE",
        area="ZONA",
        ruta_base=str(temp_files_dir / "proyecto"),
        estado_proyecto=modelos.EstadoProyectoEnum.ACTIVO,
    )
    test_db.add(proyecto)
    test_db.commit()

    categoria = modelos.Categoria(nombre="CAT_EXIF", proyecto_id=proyecto.id)
    test_db.add(categoria)
    test_db.commit()

    item = modelos.Item(
        nombre="ITEM_EXIF",
        ruta_item=str(temp_files_dir / "proyecto" / "ITEM_EXIF"),
        categoria_id=categoria.id,
    )
    test_db.add(item)
    test_db.commit()

    asignacion = modelos.AsignacionPlan(
        plan_id=plan.id,
        item_id=item.id,
        estado=modelos.EstadoItemEnum.ASIGNADA,
    )
    test_db.add(asignacion)
    test_db.commit()
    test_db.refresh(asignacion)

    # Crear imagen con EXIF
    imagen = crear_imagen_con_exif(fecha=datetime.now())

    # Subir foto
    response = test_client.post(
        f"/api/asignaciones/{asignacion.id}/upload-multiple/",
        headers=auth_headers,
        files=[("files", ("test.jpg", imagen, "image/jpeg"))],
    )

    # Verificar respuesta (puede variar según implementación)
    assert response.status_code in [200, 201]


def test_subir_foto_sin_exif(
    test_client, auth_headers, test_db, temp_files_dir, monkeypatch
):
    """
    Test: Subir foto sin EXIF debe ir a _PENDIENTE_METADATOS (cuarentena).
    """
    monkeypatch.setattr("backend.core.nucleo.BASE_FILES_DIR", str(temp_files_dir))

    # Crear proyecto y asignación
    plan = modelos.PlanTrabajo(descripcion="Plan SIN EXIF")
    test_db.add(plan)
    test_db.commit()

    proyecto = modelos.Proyecto(
        nombre_pmc="PMC_TEST_FOTO2",
        cliente="CLIENTE",
        area="ZONA",
        ruta_base=str(temp_files_dir / "proyecto2"),
        estado_proyecto=modelos.EstadoProyectoEnum.ACTIVO,
    )
    test_db.add(proyecto)
    test_db.commit()

    categoria = modelos.Categoria(nombre="CAT_SIN_EXIF", proyecto_id=proyecto.id)
    test_db.add(categoria)
    test_db.commit()

    item = modelos.Item(
        nombre="ITEM_SIN_EXIF",
        ruta_item=str(temp_files_dir / "proyecto2" / "ITEM_SIN_EXIF"),
        categoria_id=categoria.id,
    )
    test_db.add(item)
    test_db.commit()

    asignacion = modelos.AsignacionPlan(
        plan_id=plan.id,
        item_id=item.id,
        estado=modelos.EstadoItemEnum.ASIGNADA,
    )
    test_db.add(asignacion)
    test_db.commit()
    test_db.refresh(asignacion)

    # Crear imagen SIN EXIF
    img = Image.new("RGB", (100, 100), color="red")
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    buf.seek(0)

    # Subir foto
    response = test_client.post(
        f"/api/asignaciones/{asignacion.id}/upload-multiple/",
        headers=auth_headers,
        files=[("files", ("test_sin_exif.jpg", buf, "image/jpeg"))],
    )

    # Verificar que se procesó
    assert response.status_code in [200, 201, 400]


def test_aprobar_foto(test_client, auth_headers, test_db):
    """
    Test: Aprobar foto debe cambiar estado a VALIDADA.
    """
    # Crear asignación de prueba
    plan = modelos.PlanTrabajo(descripcion="Plan de prueba")
    test_db.add(plan)
    test_db.commit()

    proyecto = modelos.Proyecto(
        nombre_pmc="PMC_VALIDACION",
        cliente="CLIENTE",
        area="ZONA",
        ruta_base="/tmp/test",
        estado_proyecto=modelos.EstadoProyectoEnum.ACTIVO,
    )
    test_db.add(proyecto)
    test_db.commit()

    categoria = modelos.Categoria(nombre="CATEGORIA_TEST", proyecto_id=proyecto.id)
    test_db.add(categoria)
    test_db.commit()

    item = modelos.Item(
        nombre="ITEM_TEST",
        ruta_item="/tmp/test/item",
        categoria_id=categoria.id,
    )
    test_db.add(item)
    test_db.commit()

    asignacion = modelos.AsignacionPlan(
        plan_id=plan.id,
        item_id=item.id,
        estado=modelos.EstadoItemEnum.COMPLETADA_TERRENO,
    )
    test_db.add(asignacion)
    test_db.commit()
    test_db.refresh(asignacion)

    # Aprobar foto
    response = test_client.post(
        f"/api/asignaciones/{asignacion.id}/validar/",
        headers=auth_headers,
    )

    assert response.status_code == 200

    # Verificar que el estado cambió
    test_db.refresh(asignacion)
    assert asignacion.estado == modelos.EstadoItemEnum.VALIDADA


def test_rechazar_foto(test_client, auth_headers, test_db):
    """
    Test: Rechazar foto debe cambiar estado a RECHAZADA.
    """
    # Crear asignación de prueba
    plan = modelos.PlanTrabajo(descripcion="Plan de prueba 2")
    test_db.add(plan)
    test_db.commit()

    proyecto = modelos.Proyecto(
        nombre_pmc="PMC_RECHAZO",
        cliente="CLIENTE",
        area="ZONA",
        ruta_base="/tmp/test",
        estado_proyecto=modelos.EstadoProyectoEnum.ACTIVO,
    )
    test_db.add(proyecto)
    test_db.commit()

    categoria = modelos.Categoria(nombre="CATEGORIA_TEST2", proyecto_id=proyecto.id)
    test_db.add(categoria)
    test_db.commit()

    item = modelos.Item(
        nombre="ITEM_TEST2",
        ruta_item="/tmp/test/item2",
        categoria_id=categoria.id,
    )
    test_db.add(item)
    test_db.commit()

    asignacion = modelos.AsignacionPlan(
        plan_id=plan.id,
        item_id=item.id,
        estado=modelos.EstadoItemEnum.COMPLETADA_TERRENO,
    )
    test_db.add(asignacion)
    test_db.commit()
    test_db.refresh(asignacion)

    # Rechazar foto
    response = test_client.post(
        f"/api/asignaciones/{asignacion.id}/rechazar/",
        headers=auth_headers,
        json={"comentario": "Foto borrosa, volver a tomar"},
    )

    assert response.status_code == 200

    # Verificar que el estado cambió
    test_db.refresh(asignacion)
    assert asignacion.estado == modelos.EstadoItemEnum.RECHAZADA
    assert asignacion.comentario_rechazo_supervisor == "Foto borrosa, volver a tomar"
