# Guia rapida: cambios locales -> GitHub -> despliegue en servidor

## Objetivo
Este documento explica el flujo completo para: clonar el proyecto en tu PC, hacer cambios, subirlos a GitHub y que el servidor se actualice automaticamente.

## Requisitos
- Cuenta de GitHub con acceso al repositorio.
- Git instalado en el PC.
- Acceso a la red donde corre el servidor (para verificar el servicio si aplica).

## Paso 1: Configuracion inicial en el PC (una sola vez)
1. Configura tu usuario de Git.

```bash
git config --global user.name "Tu Nombre"
git config --global user.email "tu@email.com"
```

2. Elige un metodo de autenticacion.

Opcion A: SSH (recomendado).

```bash
ssh-keygen -t ed25519 -C "tu@email.com"
cat ~/.ssh/id_ed25519.pub
```

Copia la llave publica y agregala en GitHub.

Opcion B: HTTPS con token.

- En GitHub genera un Personal Access Token (PAT) con permisos de repo.
- Usa ese token como password cuando Git lo pida.

3. Clona el repo.

```bash
git clone git@github.com:TU_USUARIO/TERRENEITOR.git
cd TERRENEITOR
```

## Paso 2: Flujo diario de trabajo
1. Trae lo ultimo de GitHub.

```bash
git checkout main
git pull origin main
```

2. Crea una rama para tu cambio.

```bash
git checkout -b feature/mi-cambio
```

3. Haz tus cambios en el codigo.

4. (Opcional pero recomendado) corre tests localmente.

```bash
cd code
pytest tests/ -v
```

5. Revisa el estado, agrega y commitea.

```bash
git status
git add <archivos>
git commit -m "descripcion clara del cambio"
```

6. Sube la rama a GitHub.

```bash
git push origin feature/mi-cambio
```

7. Abre un Pull Request (PR) hacia `main` en GitHub.

## Paso 3: Despliegue automatico al servidor
Este repo tiene un workflow que, al hacer push a `main`, reinicia el servicio en el servidor.

Flujo recomendado:
1. Abrir PR y esperar que el CI quede verde.
2. Hacer merge del PR a `main`.
3. El push a `main` dispara el workflow de deploy.

## Paso 4: Verificacion en GitHub
1. Ve a la pestaña Actions.
2. Abre el workflow de CI y el de Deploy.
3. Confirma que ambos estan en verde.

## Paso 5: Verificacion en el servidor
En el servidor, revisa el estado del servicio:

```bash
sudo systemctl status terreneitor
```

Si hubo fallo, revisa logs:

```bash
sudo journalctl -u terreneitor -n 50
```

## Errores comunes y que hacer
1. Push dice "Everything up-to-date".
Eso significa que no hay commits nuevos. Debes hacer commit primero.

2. CI se queda pegado.
Revisar el ultimo step en Actions. Si es un servicio externo (como Codecov), puede colgarse sin logs.

3. El deploy no corre.
Verifica que el workflow de Deploy exista y que el runner self-hosted este online.

## Atajos utiles
- Ver ramas: `git branch`
- Cambiar de rama: `git checkout nombre_rama`
- Ver ultimos commits: `git log --oneline -5`
- Deshacer cambios no committeados: `git restore <archivo>`
