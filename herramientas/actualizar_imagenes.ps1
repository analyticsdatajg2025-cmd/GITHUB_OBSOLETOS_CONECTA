# =====================================================================
#  Actualizar cache de imagenes - Flyers Obsoletos
#  Se ejecuta en la laptop (Windows) con doble clic en actualizar_imagenes.bat
#
#  Que hace:
#   1. Lee la lista de imagenes que necesitan los flyers (la publica el workflow).
#   2. Baja el ZIP de cache actual desde el release "imagenes-cache" de GitHub.
#   3. Descarga desde lacuracao.pe solo las imagenes que faltan (con tu red),
#      las reduce a 520 px en JPEG y borra las que ya no se usan.
#   4. Sube el ZIP nuevo al release (reemplaza el anterior, no ocupa espacio extra).
# =====================================================================
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
# Usa el proxy corporativo con tus credenciales de Windows, si lo hay
if ([System.Net.WebRequest]::DefaultWebProxy) {
    [System.Net.WebRequest]::DefaultWebProxy.Credentials = [System.Net.CredentialCache]::DefaultNetworkCredentials
}
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.IO.Compression.FileSystem

$Owner    = "analyticsdatajg2025-cmd"
$Repo     = "GITHUB_OBSOLETOS_CONECTA"
$Tag      = "imagenes-cache"
$ZipName  = "imagenes_cache.zip"
$ListaUrl = "https://$Owner.github.io/$Repo/imagenes_necesarias.txt"
$Api      = "https://api.github.com/repos/$Owner/$Repo"
$Lado     = 520   # px maximos (lo que ocupa la foto en el flyer)

function Escribir($texto, $color = "White") { Write-Host $texto -ForegroundColor $color }

# ---------- Token de GitHub (se guarda cifrado con tu usuario de Windows) ----------
$CfgDir  = Join-Path $env:APPDATA "FlyersObsoletos"
$TokFile = Join-Path $CfgDir "token.txt"
if (-not (Test-Path $CfgDir)) { New-Item -ItemType Directory -Path $CfgDir | Out-Null }
if (Test-Path $TokFile) {
    $sec = Get-Content $TokFile | ConvertTo-SecureString
} else {
    Escribir "Primera vez: pega tu token de GitHub (no se vera al escribir) y presiona Enter." "Yellow"
    $sec = Read-Host -AsSecureString "Token"
    $sec | ConvertFrom-SecureString | Set-Content $TokFile
}
$Token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
$H = @{
    "Authorization"        = "Bearer $Token"
    "Accept"               = "application/vnd.github+json"
    "X-GitHub-Api-Version" = "2022-11-28"
    "User-Agent"           = "flyers-obsoletos-cache"
}

# PowerShell 5.1 no envia el cuerpo en UTF-8 por defecto: GitHub responde 400 si hay tildes
# Ojo: la coma en "return ," evita que PowerShell convierta el byte[] en una lista de numeros
function Json-Utf8($objeto) {
    [byte[]]$bytes = [System.Text.Encoding]::UTF8.GetBytes(($objeto | ConvertTo-Json -Depth 5))
    return ,$bytes
}

function Md5Hex([string]$s) {
    $md5 = [System.Security.Cryptography.MD5]::Create()
    $bytes = $md5.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($s))
    return (($bytes | ForEach-Object { $_.ToString("x2") }) -join "")
}

function Guardar-Miniatura([string]$origen, [string]$destino) {
    $img = [System.Drawing.Image]::FromFile($origen)
    try {
        $escala = [Math]::Min(1.0, [Math]::Min($Lado / $img.Width, $Lado / $img.Height))
        $w = [int][Math]::Max(1, [Math]::Round($img.Width * $escala))
        $h = [int][Math]::Max(1, [Math]::Round($img.Height * $escala))
        $bmp = New-Object System.Drawing.Bitmap $w, $h
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        $g.Clear([System.Drawing.Color]::White)
        $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
        $g.DrawImage($img, 0, 0, $w, $h)
        $g.Dispose()
        $codec = [System.Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() | Where-Object { $_.MimeType -eq "image/jpeg" }
        $params = New-Object System.Drawing.Imaging.EncoderParameters 1
        $params.Param[0] = New-Object System.Drawing.Imaging.EncoderParameter ([System.Drawing.Imaging.Encoder]::Quality), ([long]85)
        $bmp.Save($destino, $codec, $params)
        $bmp.Dispose()
    } finally { $img.Dispose() }
}

$Trabajo = Join-Path $env:TEMP "flyers_obsoletos_cache"
if (Test-Path $Trabajo) { Remove-Item $Trabajo -Recurse -Force }
$Carpeta = Join-Path $Trabajo "imagenes"
New-Item -ItemType Directory -Path $Carpeta -Force | Out-Null

try {
    # ---------- 1. Lista de imagenes necesarias ----------
    Escribir "1/4 Leyendo la lista de imagenes que necesitan los flyers..."
    $resp = Invoke-WebRequest -Uri ($ListaUrl + "?t=" + [DateTime]::Now.Ticks) -UseBasicParsing
    $texto = $resp.Content
    if ($texto -is [byte[]]) { $texto = [System.Text.Encoding]::UTF8.GetString($texto) }
    $urls = @($texto -split "`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ -like "http*" } | Sort-Object -Unique)
    $necesarias = @{}
    foreach ($u in $urls) { $necesarias[(Md5Hex $u) + ".jpg"] = $u }
    Escribir "    $($urls.Count) imagenes necesarias."

    # ---------- 2. Cache actual (release) ----------
    Escribir "2/4 Bajando la cache actual de GitHub..."
    $release = $null
    try { $release = Invoke-RestMethod -Uri "$Api/releases/tags/$Tag" -Headers $H }
    catch {
        if ($_.Exception.Response -and [int]$_.Exception.Response.StatusCode -eq 404) {
            [byte[]]$body = Json-Utf8 @{ tag_name = $Tag; name = "Cache de imagenes (no borrar)";
                       body = "ZIP con las imagenes de productos para los flyers. Lo actualiza herramientas/actualizar_imagenes.bat.";
                       make_latest = "false" }
            $release = Invoke-RestMethod -Method Post -Uri "$Api/releases" -Headers $H -Body $body -ContentType "application/json; charset=utf-8"
            Escribir "    Release '$Tag' creado (primera vez)."
        } else { throw }
    }
    $assetViejo = $release.assets | Where-Object { $_.name -eq $ZipName }
    if ($assetViejo) {
        $zipViejo = Join-Path $Trabajo "viejo.zip"
        # URL publica del archivo (el repo es publico); sin token para evitar errores en la redireccion
        Invoke-WebRequest -Uri $assetViejo.browser_download_url -OutFile $zipViejo -UseBasicParsing
        [System.IO.Compression.ZipFile]::ExtractToDirectory($zipViejo, $Carpeta)
    }
    $existentes = @(Get-ChildItem $Carpeta -Filter *.jpg | ForEach-Object { $_.Name })
    Escribir "    En cache: $($existentes.Count) imagenes."

    # Borrar las que ya no se usan
    $borradas = 0
    foreach ($n in $existentes) {
        if (-not $necesarias.ContainsKey($n)) { Remove-Item (Join-Path $Carpeta $n); $borradas++ }
    }

    # ---------- 3. Descargar las que faltan ----------
    $faltan = @($necesarias.Keys | Where-Object { -not (Test-Path (Join-Path $Carpeta $_)) })
    Escribir "3/4 Descargando $($faltan.Count) imagenes nuevas desde lacuracao.pe..."
    $ok = 0; $fallos = @{}; $i = 0; $tmp = Join-Path $Trabajo "descarga.tmp"
    foreach ($n in $faltan) {
        $i++
        $u = $necesarias[$n]
        try {
            Invoke-WebRequest -Uri $u -OutFile $tmp -UseBasicParsing -TimeoutSec 30
            try { Guardar-Miniatura $tmp (Join-Path $Carpeta $n) }
            catch {
                # Formatos que Windows no puede reducir (p. ej. .webp): se guardan tal cual,
                # el workflow (Python/Pillow) si los lee.
                Copy-Item $tmp (Join-Path $Carpeta $n) -Force
            }
            $ok++
        } catch {
            $motivo = "error"
            if ($_.Exception.Response) { $motivo = "HTTP " + [int]$_.Exception.Response.StatusCode }
            elseif ($_.Exception -is [System.OutOfMemoryException] -or $_.Exception.Message -match "memoria|memory") { $motivo = "formato no soportado" }
            else { $motivo = $_.Exception.GetType().Name }
            if (-not $fallos.ContainsKey($motivo)) { $fallos[$motivo] = @() }
            $fallos[$motivo] += $u
        }
        if ($i % 50 -eq 0) { Escribir "    $i / $($faltan.Count)..." }
        # Si las primeras 20 fallan por bloqueo, tu red tambien esta bloqueada: no seguir
        if ($i -eq 20 -and $ok -eq 0 -and ($fallos.ContainsKey("HTTP 426") -or $fallos.ContainsKey("HTTP 403"))) {
            Escribir "" ; Escribir "lacuracao.pe tambien esta bloqueando las descargas desde esta laptop." "Red"
            Escribir "Esta opcion no funcionara: hay que pedir a TI que autorice el proceso en Fastly." "Red"
            Read-Host "Presiona Enter para cerrar"; exit 1
        }
    }
    Escribir "    Descargadas: $ok. Borradas por no usarse: $borradas." "Green"
    foreach ($k in $fallos.Keys) { Escribir "    Fallaron $($fallos[$k].Count) por $k. Ejemplo: $($fallos[$k][0])" "Yellow" }

    # ---------- 4. Subir ZIP nuevo ----------
    $total = @(Get-ChildItem $Carpeta -Filter *.jpg).Count
    if ($ok -eq 0 -and $borradas -eq 0 -and $assetViejo) {
        Escribir "4/4 No hubo cambios. La cache ya estaba al dia ($total imagenes)." "Green"
    } else {
        Escribir "4/4 Subiendo la cache a GitHub ($total imagenes)..."
        $zipNuevo = Join-Path $Trabajo $ZipName
        [System.IO.Compression.ZipFile]::CreateFromDirectory($Carpeta, $zipNuevo)
        $mb = [Math]::Round((Get-Item $zipNuevo).Length / 1MB, 1)
        $tmpName = "imagenes_cache_nuevo.zip"
        $previo = $release.assets | Where-Object { $_.name -eq $tmpName }
        if ($previo) { Invoke-RestMethod -Method Delete -Uri "$Api/releases/assets/$($previo.id)" -Headers $H | Out-Null }
        $up = "https://uploads.github.com/repos/$Owner/$Repo/releases/$($release.id)/assets?name=$tmpName"
        $nuevo = Invoke-RestMethod -Method Post -Uri $up -Headers $H -InFile $zipNuevo -ContentType "application/zip"
        if ($assetViejo) { Invoke-RestMethod -Method Delete -Uri "$Api/releases/assets/$($assetViejo.id)" -Headers $H | Out-Null }
        [byte[]]$ren = Json-Utf8 @{ name = $ZipName }
        Invoke-RestMethod -Method Patch -Uri "$Api/releases/assets/$($nuevo.id)" -Headers $H -Body $ren -ContentType "application/json; charset=utf-8" | Out-Null
        Escribir "    Listo: $ZipName subido ($mb MB)." "Green"
    }
    Escribir ""
    Escribir "Terminado. Los flyers usaran estas imagenes en la proxima ejecucion del workflow (3 PM) o al correrlo a mano." "Green"
}
catch {
    Escribir "" ; Escribir "ERROR: $($_.Exception.Message)" "Red"
    if ($_.ErrorDetails -and $_.ErrorDetails.Message) { Escribir "Detalle: $($_.ErrorDetails.Message)" "Red" }
    if ($_.Exception.Response -and [int]$_.Exception.Response.StatusCode -eq 401) {
        Escribir "El token no es valido o vencio. Se borrara para que pegues uno nuevo la proxima vez." "Yellow"
        Remove-Item $TokFile -ErrorAction SilentlyContinue
    }
    Read-Host "Presiona Enter para cerrar"; exit 1
}
finally {
    if (Test-Path $Trabajo) { Remove-Item $Trabajo -Recurse -Force -ErrorAction SilentlyContinue }
}
Read-Host "Presiona Enter para cerrar"
