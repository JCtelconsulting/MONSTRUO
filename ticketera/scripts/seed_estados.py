"""Siembra tickets de PRUEBA en ticketera, uno por cada estado/proceso posible.

Sirve para validar el comportamiento antes de PROD (ver el bug de pendiente_cliente
arreglado, el flujo pendiente_gerencia, las areas nuevas, y datos para el reporte de
atendidos). Solo DEV.

Uso:
  docker exec monstruo-dev-ticketera python /app/ticketera/scripts/seed_estados.py
"""
from ticketera.backend.services import service as svc

ACTOR = "qa.seed@telconsulting.cl"
PREFIX = "[SEED]"


def crear(titulo, tipo="incidencia", categoria="sistemas", severidad="media", cliente=None):
    t = svc.create_ticket(
        titulo=f"{PREFIX} {titulo}",
        descripcion=f"Ticket de prueba sembrado: {titulo}",
        creador_id=ACTOR,
        severidad=severidad,
        tipo=tipo,
        categoria=categoria,
        origen_email="cliente.seed@example.com",
        cliente_nombre=cliente,
    )
    return t["id"]


def asignar(tid):
    try:
        svc.claim_ticket(tid, ACTOR, "admin")
        return True
    except Exception:
        return mover(tid, "asignado")


def mover(tid, *subs):
    ok = True
    for s in subs:
        try:
            svc.transition_ticket(ticket_id=tid, to_subestado=s, actor_id=ACTOR, actor_role="admin", motivo="seed")
        except Exception as e:
            print(f"   ! ticket {tid} -> {s}: {e}")
            ok = False
    return ok


def main():
    print("== Sembrando tickets de prueba (todos los estados) ==")
    casos = []

    # Recibido (recien creado, sin asignar)
    casos.append(("Incidencia recibida (sin asignar)", crear("Incidencia recibida", "incidencia", "redes")))

    # Asignado
    t = crear("Incidencia asignada", "incidencia", "sistemas"); asignar(t)
    casos.append(("Asignado", t))

    # En progreso
    t = crear("En progreso", "incidencia", "ejecucion"); asignar(t); mover(t, "en_progreso")
    casos.append(("En progreso", t))

    # Pendiente cliente (el bug que se arreglo: no debe rebotar a abierto)
    t = crear("Pendiente cliente", "requerimiento", "sistemas"); asignar(t); mover(t, "en_progreso", "pendiente_cliente")
    casos.append(("Pendiente cliente", t))

    # Pendiente gerencia (feature nueva: aprobar/rechazar)
    t = crear("Pendiente gerencia (requerimiento interno)", "requerimiento", "gerencia"); asignar(t); mover(t, "en_progreso", "pendiente_gerencia")
    casos.append(("Pendiente gerencia", t))

    # Pendiente compra (area bodega nueva)
    t = crear("Pendiente compra (bodega)", "incidencia", "bodega"); asignar(t); mover(t, "en_progreso", "pendiente_compra")
    casos.append(("Pendiente compra", t))

    # Resuelto (con resolved_at -> cuenta en el reporte de atendidos)
    t = crear("Resuelto", "incidencia", "redes", cliente="Cliente Demo SA"); asignar(t); mover(t, "en_progreso", "resuelto")
    casos.append(("Resuelto", t))

    # Cerrado
    t = crear("Cerrado", "incidencia", "sistemas", cliente="Cliente Demo SA"); asignar(t); mover(t, "en_progreso", "resuelto", "cerrado")
    casos.append(("Cerrado", t))

    # Resuelto de otro cliente (para el desglose por cliente del reporte)
    t = crear("Resuelto otro cliente", "requerimiento", "ejecucion", cliente="Constructora Andes"); asignar(t); mover(t, "en_progreso", "resuelto")
    casos.append(("Resuelto (otro cliente)", t))

    # Cambio en analisis/aprobacion (flujo de cambio)
    t = crear("Cambio en analisis", "cambio", "sistemas"); asignar(t); mover(t, "en_analisis")
    casos.append(("Cambio en analisis", t))

    print("\n== Resumen (estado real desde DB) ==")
    for label, tid in casos:
        try:
            tk = svc.get_ticket(tid)
            print(f"  #{tid:>4}  {label:<34}  estado={tk.get('estado'):<12} subestado={tk.get('subestado')}")
        except Exception as e:
            print(f"  #{tid}  {label}: error {e}")
    print(f"\nListo: {len(casos)} tickets sembrados.")


if __name__ == "__main__":
    main()
