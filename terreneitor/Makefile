# =============================================================================
# Terreneitor - Makefile
# Atajos para operar la app sin recordar comandos largos.
# Uso: `make` lista todos los targets, `make <target>` ejecuta uno.
# =============================================================================

# Variables (cambiar acá si algun dia cambia el contenedor o las rutas).
CONTAINER  = terreneitor_app
PORT       = 8005
DB_FILE    = data/db/terreneitor.db
LOG_FILE   = logs/backup.log

# .DEFAULT_GOAL hace que `make` (sin argumentos) ejecute `help`.
.DEFAULT_GOAL := help

# .PHONY le dice a make que estos no son archivos, sino comandos.
# Sin esto, si existiera un archivo llamado "start" o "test" en la raiz,
# `make start` no haria nada porque make creeria que ya esta hecho.
.PHONY: help start stop restart rebuild logs status \
        test test-e2e lint format \
        backup backup-tail db-shell shell \
        sync-dev clean-papelera

# =============================================================================
# AYUDA
# =============================================================================

help:  ## Muestra esta ayuda
	@echo ""
	@echo "  Terreneitor - Comandos disponibles:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""

# =============================================================================
# CICLO DE VIDA DEL CONTENEDOR
# =============================================================================

start:  ## Levanta el contenedor de la app
	docker start $(CONTAINER) && echo "Contenedor iniciado en puerto $(PORT)"

stop:  ## Detiene el contenedor (sin removerlo)
	docker stop $(CONTAINER)

rebuild:  ## Rebuild de la imagen Docker (cambios en Dockerfile o requirements)
	bash ops/scripts/despliegue/iniciar.sh

restart:  ## Reinicia el contenedor (aplica cambios de codigo Python sin rebuild)
	docker restart $(CONTAINER)
	@echo "Esperando que el backend este listo..."
	@for i in 1 2 3 4 5 6 7 8 9 10; do \
		code=$$(curl -s -o /dev/null -w "%{http_code}" http://localhost:$(PORT)/api/auth/whoami || echo "000"); \
		if [ "$$code" = "200" ]; then \
			echo "OK - app respondiendo en http://localhost:$(PORT)"; \
			exit 0; \
		fi; \
		sleep 1; \
	done; \
	echo "ERROR - app no responde tras 10s"; \
	exit 1

logs:  ## Sigue los logs del contenedor en vivo (Ctrl+C para salir)
	docker logs -f --tail 50 $(CONTAINER)

status:  ## Estado de salud: docker, app, datos
	@echo "=== Contenedor ==="
	@docker ps --filter name=$(CONTAINER) --format "{{.Names}}  {{.Status}}"
	@echo ""
	@echo "=== App HTTP ==="
	@curl -s -o /dev/null -w "  /api/auth/whoami => HTTP %{http_code}\n" http://localhost:$(PORT)/api/auth/whoami
	@echo ""
	@echo "=== Datos ==="
	@sqlite3 $(DB_FILE) "SELECT '  proyectos: '||COUNT(*) FROM proyectos;"
	@sqlite3 $(DB_FILE) "SELECT '  planes:    '||COUNT(*) FROM planes_trabajo;"
	@sqlite3 $(DB_FILE) "SELECT '  users:     '||COUNT(*) FROM users;"

# =============================================================================
# TESTS Y CALIDAD
# =============================================================================

test:  ## Corre los unit tests del backend (dentro del contenedor)
	docker exec $(CONTAINER) sh -c "cd /app && PYTHONPATH=. TERRENEITOR_TEST_MODE=1 python -m pytest backend/tests/ -v"

test-e2e:  ## Corre los tests E2E con Playwright (requiere chromium local)
	@echo "Recordatorio: el backend tiene que estar corriendo (make start)"
	cd e2e && uvx --with playwright --with pytest --with pytest-playwright pytest -c pytest.ini --tb=short

lint:  ## Corre todos los pre-commit hooks (Black, Ruff, Prettier)
	pre-commit run --all-files

format:  ## Formatea Python (black) y JS/CSS (prettier) sin chequeos
	@docker exec $(CONTAINER) sh -c "cd /app && python -m black backend/" || true
	@docker exec $(CONTAINER) sh -c "cd /app && python -m ruff check --fix backend/" || true
	@uvx prettier --write "frontend/modulos/**/*.js" "frontend/modulos/**/*.css" "frontend/modulos/**/*.html"

# =============================================================================
# UTILIDADES
# =============================================================================

backup:  ## Corre un backup manual de prod a Drive
	bash ops/scripts/backup/terreneitor_integral_backup_prod.sh

backup-tail:  ## Muestra las ultimas lineas del log de backup
	tail -30 $(LOG_FILE)

db-shell:  ## Abre sqlite3 en la DB de prod (read-only)
	sqlite3 -readonly $(DB_FILE)

shell:  ## Entra al contenedor con bash interactivo
	docker exec -it $(CONTAINER) /bin/bash

# =============================================================================
# GIT / DEPLOYMENT
# =============================================================================

sync-dev:  ## Sincroniza la rama dev con main (force-push)
	git push origin main:dev

# =============================================================================
# LIMPIEZA
# =============================================================================

clean-papelera:  ## Borra _papelera_refactor/ (CUIDADO: revisar primero qué hay)
	@echo "ATENCION: esto borra _papelera_refactor/ definitivamente."
	@echo "Contenido actual:"
	@ls _papelera_refactor/ 2>/dev/null || echo "  (carpeta vacia o ya borrada)"
	@echo ""
	@read -p "Confirmar borrado? (escribir SI): " confirm; \
	if [ "$$confirm" = "SI" ]; then \
		rm -rf _papelera_refactor/; \
		echo "Borrada."; \
	else \
		echo "Cancelado."; \
	fi
