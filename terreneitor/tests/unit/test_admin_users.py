from terreneitor.backend import modelos
from terreneitor.backend.core.dependencias import get_db_hash


def test_admin_no_puede_eliminarse_a_si_mismo(
    test_client, test_db, test_user, auth_headers
):
    response = test_client.delete(f"/api/admin/users/{test_user.id}")

    assert response.status_code == 403
    assert response.json()["detail"] == "No puedes eliminar tu propio usuario"
    assert (
        test_db.query(modelos.User).filter(modelos.User.id == test_user.id).first()
        is not None
    )


def test_admin_puede_eliminar_a_otro_admin(
    test_client, test_db, test_user, auth_headers
):
    other_admin = modelos.User(
        email="otro-admin@terreneitor.com",
        name="Otro Admin",
        role=modelos.UserRoleEnum.ADMIN,
        hashed_password=get_db_hash("password123"),
    )
    test_db.add(other_admin)
    test_db.commit()
    test_db.refresh(other_admin)

    response = test_client.delete(f"/api/admin/users/{other_admin.id}")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert (
        test_db.query(modelos.User).filter(modelos.User.id == other_admin.id).first()
        is None
    )
    assert (
        test_db.query(modelos.User).filter(modelos.User.id == test_user.id).first()
        is not None
    )
