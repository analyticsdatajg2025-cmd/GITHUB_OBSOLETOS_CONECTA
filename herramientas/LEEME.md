# Actualizar imágenes de los flyers (Windows)

Una sola ejecución actualiza los dos procesos: **OBSOLETOS** y **LENTO MOVIMIENTO**.

lacuracao.pe bloquea las descargas automáticas desde GitHub (error 426), pero sí
permite descargarlas desde la red de la empresa. Esta herramienta descarga las
imágenes desde tu laptop y las deja en GitHub para que el workflow las use.

## Configuración (una sola vez)

1. **Crear un token de GitHub** (con la cuenta `analyticsdatajg2025-cmd`):
   - Entra a https://github.com/settings/personal-access-tokens/new
   - *Token name*: `flyers-imagenes`. *Expiration*: 1 año (o lo que permita tu empresa).
   - *Repository access*: **Only select repositories** → `GITHUB_OBSOLETOS_CONECTA` **y** `GITHUB_LENTO-MOVIMIENTO_CONECTA`.
   - Si ya tenías un token solo con OBSOLETOS: en https://github.com/settings/personal-access-tokens
     ábrelo, pulsa *Edit*, agrega `GITHUB_LENTO-MOVIMIENTO_CONECTA` y guarda (el valor del token no cambia).
   - *Permissions* → *Repository permissions* → **Contents: Read and write**.
   - *Generate token* y copia el valor (empieza con `github_pat_`).
2. **Descargar la herramienta**: en el repo, botón verde **Code → Download ZIP**,
   descomprime y copia la carpeta `herramientas` a donde quieras (por ejemplo, Escritorio).

## Uso (cada vez que cambie el inventario de obsoletos o de lento movimiento)

1. Doble clic en **`actualizar_imagenes.bat`**.
2. La primera vez te pide el token: pégalo (no se ve al escribir) y Enter.
   Queda guardado cifrado con tu usuario de Windows; no lo vuelve a pedir.
3. Espera a que diga **"Terminado"** (la primera vez puede tardar 10-20 min; después, pocos minutos).
4. Listo: el workflow de las 3 PM usará las imágenes. Si quieres verlo ya,
   ejecuta el workflow a mano en GitHub → Actions → *Run workflow*.

## Qué ocupa

- Solo las imágenes de los productos que están hoy en cada inventario, a 520 px en JPEG:
  OBSOLETOS ~1200 imágenes (~28 MB) y LENTO MOVIMIENTO ~2100 (~50 MB), cada uno en un solo ZIP
  dentro del release `imagenes-cache` de su repo. Las imágenes repetidas se bajan una sola vez.
- Cada actualización **reemplaza** el ZIP (no se acumula) y borra las imágenes que ya no se usan.
- En la laptop no queda nada: trabaja en una carpeta temporal que se borra al terminar.

## Si algo falla

- *"lacuracao.pe también está bloqueando las descargas desde esta laptop"*: tu red también
  está bloqueada; hay que pedir a TI que autorice el proceso en Fastly.
- *Token no válido o vencido*: se borra solo; vuelve a ejecutar y pega un token nuevo.
- *El token no tiene permiso sobre ...*: agrega ese repositorio al token (ver Configuración, paso 1).
- *Aún no existe la lista de imágenes de ...*: ejecuta primero ese workflow en GitHub (Actions → Run workflow).
- *La ventana se cierra o dice que no se pueden ejecutar scripts*: tu empresa bloquea PowerShell;
  pide a TI que permita ejecutar `actualizar_imagenes.ps1`.
