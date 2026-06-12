# Regla de Oro para el Agente (Git)

Esta es la directriz principal de control de versiones para Terreneitor. Todo agente de desarrollo (IA o Humano) DEBE seguir este flujo de trabajo de forma autónoma.

## 1. Commits Automáticos (Cambios Pequeños)

- Si la tarea implica cambios menores (1-3 archivos o mejoras puntuales), el agente **DEBE realizar un commit automático** antes de dar por finalizada su respuesta.
- Formato sugerido: `git add . && git commit -m "tipo: descripción clara del cambio"`.

## 2. Flujo de Ramas (Cambios Grandes / Funcionalidades)

- Si el usuario solicita una nueva funcionalidad o una reestructuración masiva, el agente **DEBE**:
  1. Crear automáticamente una rama de trabajo: `git checkout -b feature/nombre-cambio` o `refactor/nombre-cambio`.
  2. Realizar los cambios necesarios y comitear dentro de esa rama.
  3. **Integración Autónoma**: Una vez finalizados y probados los cambios, el agente debe volver a la rama principal e integrar todo:

     ```bash
     git checkout main
     git merge feature/nombre-cambio
     git branch -d feature/nombre-cambio
     ```

- Este proceso debe realizarse sin esperar a que el usuario lo pida paso a paso.

## 3. Mensajes de Commit

Se debe usar el estándar **Conventional Commits**:

- `feat`: Nuevas funciones.
- `fix`: Corrección de errores.
- `refactor`: Cambios de código sin nueva funcionalidad.
- `chore`: Limpieza, mantenimiento, configuraciones.
- `docs`: Solo documentación.

---
*Objetivo: Mantener la raíz limpia y el historial de Git siempre actualizado y ordenado sin intervención manual del usuario.*
