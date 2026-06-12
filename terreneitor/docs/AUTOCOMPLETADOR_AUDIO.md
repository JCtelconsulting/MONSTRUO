# Autocompletador por audio (IA) — diseño por fases

**Objetivo (idea de Juan):** el técnico en terreno sube las **fotos** + **un audio
completo** (hablado natural, no dictado), y una **IA** entiende lo que hizo y
**propone el orden y la estructura del informe** Terreneitor — qué fotos
corresponden a cada hito, en qué categoría, con comentarios sugeridos — acotado
al **contexto del trabajo pedido** y a los 7 casos de uso de Diego. No es una
transcripción literal: es interpretación + estructuración.

> Estado: DISEÑADO. Requiere claves de API para activarse (ver Fase 0). La app
> ya tuvo IA y se purgó (marzo 2026); `openai>=1.54.0` sigue en requirements y la
> tabla `ia_logs` existe — reaprovechables.

## Arquitectura (3 piezas)

```
[Terreno] graba/sube audio + fotos  ─►  POST /api/ia/autocompletar
                                            │
                          ┌─────────────────┴───────────────────┐
                          ▼                                       ▼
              (1) STT: Whisper (openai)              (2) Contexto del proyecto
                  audio ─► transcripción                 categorias/items + caso de uso
                          │                                       │
                          └──────────────┬────────────────────────┘
                                         ▼
                     (3) Claude (anthropic, claude-opus-4-8)
                         transcripción + FOTOS (vision) + contexto
                         ─► PROPUESTA estructurada (JSON)
                                         │
                                         ▼
            [Supervisor/Técnico] revisa, ajusta y APLICA  ─►  crea/ordena
                         asignaciones + comentarios; log en ia_logs
```

## Modo LOCAL (sin claves cloud) — elegido

Juan no tiene claves de API. Se usa IA **local**, gratis:
- **STT**: `faster-whisper` (CPU, modelo `base`/`small`) — corre en el contenedor de dev.
- **LLM + visión**: **Ollama** en el PC de Juan (la VM de dev es muy chica: 5.8 GB
  RAM, 2 cores, sin GPU → no corre un LLM útil). El backend llama a Ollama por su
  API compatible con OpenAI (`OLLAMA_BASE_URL`).

Config en `ops/environments/.env`:
```
OLLAMA_BASE_URL=http://<IP-del-PC>:11434/v1
OLLAMA_MODEL=qwen2.5vl:3b      # liviano con visión; o llava:7b / llama3.2:3b (sin visión)
WHISPER_MODEL=base             # tiny|base|small
```
Activar: `pip install faster-whisper` en el contenedor (o agregar a requirements +
rebuild), instalar Ollama en el PC (`ollama pull qwen2.5vl:3b`), abrir el puerto
11434 hacia la VM dev, setear las vars y reiniciar.

## Fase 0 — Requisitos y decisiones (referencia / alternativa cloud)

| Decisión | Opciones | Recomendado |
|---|---|---|
| STT (audio→texto) | OpenAI Whisper API · Whisper local (faster-whisper) · Google STT | **Whisper API** (openai ya está en requirements; ~US$0.006/min). Local si se quiere costo cero/offline. |
| Modelo IA propuesta | **claude-opus-4-8** (Anthropic SDK, visión para fotos, salida estructurada) | claude-opus-4-8 con adaptive thinking + structured output (JSON schema) |
| Claves | `OPENAI_API_KEY` (Whisper) + `ANTHROPIC_API_KEY` (Claude) en `ops/environments/.env` | — |
| Almacenamiento audio | `data/files/<...>/_AUDIO/` junto al proyecto | sí (igual que fotos) |
| Privacidad/costo | el audio + fotos van a APIs externas; estimar costo por informe (~US$0.05–0.20) | feature-flag por proyecto; log de costo en `ia_logs` |

## Fase 1 — Captura (terreno)
- En el módulo terreno, junto a un plan/proyecto: botón **"Grabar relato"** (graba
  con `MediaRecorder` del navegador) o subir archivo de audio.
- Asociar el audio al plan + (opcional) a las fotos ya subidas de ese plan.
- Backend: `POST /api/ia/audio` guarda el audio en `_AUDIO/` y crea un registro.

## Fase 2 — Transcripción (STT)
- `backend/services/ia_autocompletador.py: transcribir(audio_path) -> texto`
  usando el SDK de OpenAI (Whisper). Guardar la transcripción.

## Fase 3 — Propuesta IA (Claude)
- `proponer_estructura(transcripcion, fotos[], contexto) -> propuesta`:
  - **Entrada a Claude (claude-opus-4-8)**: la transcripción + las fotos como
    imágenes (visión) + el contexto (cliente, caso de uso de los 7, categorías/
    items existentes del proyecto, convenciones de nombres).
  - **Salida estructurada** (JSON schema vía `messages.parse` / `output_config`):
    lista de hitos propuestos → para cada uno: categoría, item sugerido, qué fotos
    le corresponden (por índice), comentario sugerido, nivel de confianza.
  - **Prompt**: "entiende el relato aunque sea desordenado; mapea al caso de uso;
    propón estructura; no inventes; marca dudas". Adaptive thinking ON.
- Registrar en `ia_logs` (input tokens, output, costo, modelo, tiempo).

## Fase 4 — Revisión humana (clave)
- La propuesta NO se aplica sola: el supervisor/técnico la ve en una vista de
  revisión (acordeón hito→fotos), puede **editar** (mover fotos, cambiar
  categoría, ajustar comentarios) y luego **Aplicar**.
- Aplicar = crear/ordenar las asignaciones + escribir comentarios + asociar fotos.

## Fase 5 — Integración con el flujo
- La estructura aplicada alimenta el plan/informe normal (supervisor valida →
  genera informe → gerencia ve). El audio + transcripción quedan como adjunto del
  informe para auditoría.

## Scaffold incluido (inerte sin claves)
- `backend/services/ia_autocompletador.py`: helpers `disponible()`,
  `transcribir()`, `proponer_estructura()` — devuelven error claro si faltan claves.
- `backend/api/rutas_ia.py`: `POST /api/ia/autocompletar` (feature-flag: 503
  "IA no configurada" si faltan `ANTHROPIC_API_KEY`/`OPENAI_API_KEY`).
- Para activar: agregar las claves al `.env`, `pip install anthropic` (+ openai ya
  está), levantar, y conectar la UI de terreno (Fase 1).

## Costos estimados (orden de magnitud, por informe)
- Whisper: audio de 3–5 min ≈ US$0.02–0.03.
- Claude opus-4-8 con ~6 fotos + transcripción: ≈ US$0.05–0.15 (según fotos/largo).
- Total ≈ **US$0.07–0.18 por informe**. Configurable/medible en `ia_logs`.
