import pandas as pd
import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps
from io import BytesIO
import os
import gspread
import json
import textwrap
import urllib.parse
import time
import hashlib
from collections import Counter
from datetime import datetime, timedelta
from oauth2client.service_account import ServiceAccountCredentials
from concurrent.futures import ThreadPoolExecutor

# --- CONFIGURACIÓN DE LIENZO ---
ANCHO, ALTO = 2500, 3750
SHEET_ID = "10_VQTvW_Dkpg1rQ-nq2vkATwTwxmoFhqfUIKqxv6Aow"
USUARIO_GITHUB = "analyticsdatajg2025-cmd" 
REPO_NOMBRE = "GITHUB_OBSOLETOS_CONECTA"
URL_BASE_PAGES = f"https://{USUARIO_GITHUB}.github.io/{REPO_NOMBRE}/flyers/"

# --- RUTAS DE FUENTES ---
FONT_BOLD_COND = "Mark Simonson - Proxima Nova Alt Condensed Bold.otf"
FONT_EXTRABOLD_COND = "Mark Simonson - Proxima Nova Alt Condensed Extrabold.otf"
FONT_REGULAR_COND = "Mark Simonson - Proxima Nova Alt Condensed Regular.otf"
FONT_EXTRABOLD = "Mark Simonson - Proxima Nova Extrabold.otf"
FONT_SEMIBOLD = "Mark Simonson - Proxima Nova Semibold.otf"

# --- COLORES ---
LC_AMARILLO = (255, 203, 5)
LC_AMARILLO_OSCURO = (235, 180, 0)
EFE_AZUL = (0, 107, 213) 
EFE_AZUL_OSCURO = (0, 60, 150)
EFE_NARANJA = (255, 100, 0)
BLANCO = (255, 255, 255)
NEGRO = (0, 0, 0)
GRIS_MARCA = (100, 100, 100)

PDF_QUALITY = 70  # Calidad JPEG de las páginas del PDF
PDF_ANCHO = 1600  # Ancho final de cada página del PDF (px); suficiente para celular e impresión A4

output_dir = "docs/flyers"
os.makedirs(output_dir, exist_ok=True)

ahora_peru = datetime.utcnow() - timedelta(hours=5)
fecha_peru = ahora_peru.strftime("%d/%m/%Y %I:%M %p")
VERSION_LINK = ahora_peru.strftime("%Y%m%d%H%M")

def parsear_fecha(valor):
    # Acepta "30/11/2026", "2026-11-30", "30/11/2026 00:00:00" o el número de serie de Sheets (46356)
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        return pd.Timestamp("1899-12-30") + pd.Timedelta(days=float(valor))
    s = str(valor).strip()
    if not s: return pd.NaT
    if len(s) >= 10 and s[4] == "-":
        return pd.to_datetime(s[:10], format="%Y-%m-%d", errors="coerce")
    return pd.to_datetime(s.split(" ")[0], dayfirst=True, errors="coerce")

def conectar_sheets():
    info_creds = json.loads(os.environ['GOOGLE_SHEETS_JSON'])
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(info_creds, scope)
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID)

# Caché de imágenes: cada URL se descarga una sola vez (antes se bajaba una vez por tienda)
cache_imagenes = {}        # url -> bytes de la miniatura, o None si falló
fallos_imagenes = Counter() # motivo -> cantidad
ejemplos_fallo = {}         # motivo -> una URL de ejemplo

# Carpeta con imágenes ya descargadas desde la red de la empresa (herramientas/actualizar_imagenes.bat).
# El workflow la llena bajando el ZIP del release "imagenes-cache". Nombre de archivo = md5(url).jpg
CARPETA_CACHE = "imagenes_cache"
LISTA_NECESARIAS = "docs/imagenes_necesarias.txt"  # se publica en Pages

BLOQUEOS = (401, 403, 404, 410, 426, 429)  # respuestas que no mejoran reintentando
estado_descargas = {"intentadas": 0, "ok": 0, "corte": False}

def nombre_cache(url):
    return hashlib.md5(url.encode("utf-8")).hexdigest() + ".jpg"

def _bajar_y_cachear(url):
    if estado_descargas["corte"]:
        cache_imagenes[url] = None
        fallos_imagenes["omitida (servidor bloqueando)"] += 1
        return
    motivo = None
    for intento in range(3):
        try:
            res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
            if res.status_code != 200:
                motivo = f"HTTP {res.status_code}"
                if res.status_code in BLOQUEOS: break
            else:
                with Image.open(BytesIO(res.content)) as img:
                    img = img.convert("RGBA")
                    img.thumbnail((520, 520))
                    buf = BytesIO(); img.save(buf, "PNG")
                cache_imagenes[url] = buf.getvalue()
                estado_descargas["intentadas"] += 1
                estado_descargas["ok"] += 1
                return
        except Exception as e:
            motivo = type(e).__name__
        time.sleep(1 + intento)
    cache_imagenes[url] = None
    fallos_imagenes[motivo] += 1
    ejemplos_fallo.setdefault(motivo, url)
    estado_descargas["intentadas"] += 1
    # Si las primeras 30 descargas fallan todas por bloqueo del servidor, no insistir con el resto
    if estado_descargas["intentadas"] >= 30 and estado_descargas["ok"] == 0 and motivo in ("HTTP 426", "HTTP 403", "HTTP 429"):
        estado_descargas["corte"] = True

def precargar_imagenes(urls):
    urls = sorted(set(u for u in urls if u))
    # Lista que usa herramientas/actualizar_imagenes.ps1 para saber qué imágenes bajar
    os.makedirs(os.path.dirname(LISTA_NECESARIAS), exist_ok=True)
    with open(LISTA_NECESARIAS, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(urls) + "\n")

    desde_cache, faltantes = 0, []
    for u in urls:
        ruta = os.path.join(CARPETA_CACHE, nombre_cache(u))
        if os.path.exists(ruta):
            with open(ruta, "rb") as f:
                cache_imagenes[u] = f.read()
            desde_cache += 1
        else:
            faltantes.append(u)
    print(f"Imágenes: {desde_cache}/{len(urls)} tomadas de la caché ({CARPETA_CACHE}). Faltan {len(faltantes)}.")

    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(_bajar_y_cachear, faltantes))
    ok = sum(1 for u in urls if cache_imagenes.get(u))
    print(f"Imágenes: {ok}/{len(urls)} disponibles para los flyers ({estado_descargas['ok']} descargadas ahora).")
    for motivo, n in fallos_imagenes.most_common():
        print(f"  Aviso: {n} imágenes fallaron por {motivo}. Ejemplo: {ejemplos_fallo.get(motivo, '-')}")
    if estado_descargas["corte"] or (faltantes and estado_descargas["ok"] == 0):
        print("  Aviso: lacuracao.pe bloquea las descargas desde GitHub. Para completar las imágenes "
              "faltantes, ejecuta herramientas/actualizar_imagenes.bat en tu laptop.")

def descargar_imagen(url):
    data = cache_imagenes.get(url)
    if not data: return None
    return Image.open(BytesIO(data)).convert("RGBA")

def normalizar_sku(serie):
    return serie.astype(str).str.strip().str.upper().str.replace('-EX', '', regex=False)

def formatear_precio(valor):
    # Acepta números (1299, 1299.9) y textos ("S/ 1,299.90", "1.299", "1.299,90").
    # Antes se borraban todos los puntos, y 1299.90 se mostraba como 129990.
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        num = float(valor)
    else:
        original = str(valor).strip()
        s = original.replace("S/.", "").replace("S/", "").replace(" ", "").strip()
        if not s or s.lower() == "nan": return "0"
        if "," in s and "." in s:
            # El separador que aparece al final es el decimal
            if s.rfind(",") > s.rfind("."): s = s.replace(".", "").replace(",", ".")
            else: s = s.replace(",", "")
        elif "," in s:
            partes = s.split(",")
            s = s.replace(",", "") if len(partes[-1]) == 3 else s.replace(",", ".")
        elif s.count(".") > 1 or (s.count(".") == 1 and len(s.split(".")[-1]) == 3):
            s = s.replace(".", "")  # "1.299" = mil doscientos noventa y nueve
        try:
            num = float(s)
        except ValueError:
            return original  # Textos como "PRECIO DE CAJA" se muestran tal cual
    if num != num or num == 0: return "0"
    if num == int(num): return str(int(num))
    return f"{num:.2f}"

def crear_flyer(productos, tienda_nombre, flyer_count):
    es_efe = "EFE" in tienda_nombre.upper()
    color_fondo = EFE_AZUL_OSCURO if es_efe else LC_AMARILLO_OSCURO
    color_slogan_bg = EFE_AZUL if es_efe else LC_AMARILLO
    logo_path = "logo-efe-sin-fondo.png" if es_efe else "logo-lc-sin-fondo.png"
    tag_top_path = "tag-top-efe.png" if es_efe else "tag-top-lc.png"
    tienda_bg_path = "efe tienda.jpg" if es_efe else "LC-MIRAFLORES-LOGO-3D[2].jpg"
    
    flyer = Image.new('RGB', (ANCHO, ALTO), color=color_fondo)
    draw = ImageDraw.Draw(flyer)
    
    header_h = 1000
    try:
        bg = Image.open(tienda_bg_path).convert("RGBA")
        bg = ImageOps.fit(bg, (ANCHO, header_h), method=Image.Resampling.LANCZOS)
        overlay = Image.new('RGBA', (ANCHO, header_h), (0, 0, 0, 50))
        bg.paste(overlay, (0, 0), overlay)
        flyer.paste(bg, (0, 0))
    except: pass

    try:
        logo = Image.open(logo_path).convert("RGBA")
        if es_efe:
            diametro = 460
            c_x, c_y = ANCHO - diametro - 80, 40
            draw.ellipse([c_x, c_y, c_x + diametro, c_y + diametro], fill=BLANCO)
            logo_w = int(diametro * 0.85)
            logo = ImageOps.contain(logo, (logo_w, logo_w), method=Image.Resampling.LANCZOS)
            lx = c_x + (diametro - logo.width) // 2
            ly = c_y + (diametro - logo.height) // 2
            flyer.paste(logo, (lx, ly), logo)
        else:
            c_ancho, c_alto = 500, 380
            c_x, c_y = ANCHO - c_ancho - 80, 0
            draw.rounded_rectangle([c_x, c_y, c_x + c_ancho, c_y + c_alto], radius=50, fill=BLANCO)
            draw.rectangle([c_x, c_y, c_x + c_ancho, c_y + 40], fill=BLANCO) 
            logo_w = int(c_ancho * 0.85)
            logo_h = int(c_alto * 0.80)
            logo = ImageOps.contain(logo, (logo_w, logo_h), method=Image.Resampling.LANCZOS)
            lx = c_x + (c_ancho - logo.width) // 2
            ly = c_y + (c_alto - logo.height) // 2 + 10 
            flyer.paste(logo, (lx, ly), logo)
    except: pass

    f_tienda = ImageFont.truetype(FONT_EXTRABOLD_COND, 90)
    txt_tienda = tienda_nombre.upper()
    tw_t = draw.textlength(txt_tienda, font=f_tienda)
    
    if es_efe:
        draw.rounded_rectangle([ANCHO - tw_t - 150, 620, ANCHO, 800], radius=50, fill=EFE_NARANJA)
        draw.rectangle([ANCHO - 60, 620, ANCHO, 800], fill=EFE_NARANJA)
        draw.text((ANCHO - tw_t - 80, 655), txt_tienda, font=f_tienda, fill=BLANCO)
    else:
        p_x = ANCHO - tw_t - 250
        points = [(p_x, 720), (p_x + 100, 520), (ANCHO, 520), (ANCHO, 720)]
        draw.polygon(points, fill=NEGRO)
        draw.text((ANCHO - tw_t - 100, 570), txt_tienda, font=f_tienda, fill=LC_AMARILLO)

    f_fecha = ImageFont.truetype(FONT_BOLD_COND, 45)
    txt_gen = f"Generado: {fecha_peru}"
    tw_g = draw.textlength(txt_gen, font=f_fecha)
    draw.rounded_rectangle([0, 850, tw_g + 80, 960], radius=40, fill=BLANCO)
    draw.rectangle([0, 850, 50, 960], fill=BLANCO)
    draw.text((40, 880), txt_gen, font=f_fecha, fill=NEGRO)

    f_slogan = ImageFont.truetype(FONT_EXTRABOLD, 105)
    slogan_txt = "¡APROVECHA ESTAS INCREÍBLES OFERTAS!"
    sw = draw.textlength(slogan_txt, font=f_slogan)
    draw.rectangle([0, 1030, ANCHO, 1260], fill=color_slogan_bg)
    draw.text(((ANCHO-sw)//2, 1085), slogan_txt, font=f_slogan, fill=BLANCO if es_efe else NEGRO)

    anchos = [110, 1300]
    altos = [1350, 2150, 2950] 
    f_marca_prod = ImageFont.truetype(FONT_SEMIBOLD, 50)
    f_sku_prod = ImageFont.truetype(FONT_BOLD_COND, 55)

    for i, prod in enumerate(productos):
        if i >= 6: break
        x, y = anchos[i%2], altos[i//2]
        draw.rounded_rectangle([x, y, x+1090, y+760], radius=70, fill=BLANCO)
        
        img_p = descargar_imagen(prod.get('image_link'))
        if img_p:
            img_p.thumbnail((520, 520))
            flyer.paste(img_p, (x+30, y + (760-img_p.height)//2), img_p)

        if prod.get('es_top10', False):
            try:
                tag_top = Image.open(tag_top_path).convert("RGBA")
                tag_top.thumbnail((260, 260))
                # Coordenada ajustada: x+20, y+20 para mejor entrada visual
                flyer.paste(tag_top, (x + 20, y + 20), tag_top)
            except: pass
            
        tx = x + 570
        area_texto_w = 480 
        marca = str(prod['Nombre Marca']).upper()
        draw.text((tx + (area_texto_w - draw.textlength(marca, f_marca_prod))//2, y+50), marca, font=f_marca_prod, fill=GRIS_MARCA)
        
        titulo = str(prod['Nombre Articulo'])
        f_size = 65
        f_art_prod = ImageFont.truetype(FONT_REGULAR_COND, f_size)
        lines = textwrap.wrap(titulo, width=17)
        
        while f_size > 35:
            test_line_w = max([draw.textlength(line, font=f_art_prod) for line in lines])
            if test_line_w > area_texto_w - 15:
                f_size -= 4
                f_art_prod = ImageFont.truetype(FONT_REGULAR_COND, f_size)
            else:
                break

        ty = y + 120
        for line in lines[:4]:
            draw.text((tx, ty), line, font=f_art_prod, fill=NEGRO)
            ty += f_size + 5
            
        ty_b = y + 450
        p_val = formatear_precio(prod.get('Actualizacion Precios', 0))
        rec_color_p = EFE_AZUL if es_efe else LC_AMARILLO
        rec_color_s = EFE_NARANJA if es_efe else NEGRO
        
        draw.rounded_rectangle([tx, ty_b, tx+area_texto_w, ty_b + 140], radius=35, fill=rec_color_p)
        draw.rectangle([tx, ty_b+70, tx+area_texto_w, ty_b+140], fill=rec_color_p)
        
        p_f_size, s_f_size = 125, 75
        f_p = ImageFont.truetype(FONT_EXTRABOLD, p_f_size)
        f_s = ImageFont.truetype(FONT_REGULAR_COND, s_f_size)
        
        while p_f_size > 30 and (draw.textlength("S/ ", font=f_s) + draw.textlength(p_val, font=f_p)) > (area_texto_w - 25):
            p_f_size -= 8
            s_f_size -= 4
            f_p = ImageFont.truetype(FONT_EXTRABOLD, p_f_size)
            f_s = ImageFont.truetype(FONT_REGULAR_COND, s_f_size)

        total_p_w = draw.textlength("S/ ", font=f_s) + draw.textlength(p_val, font=f_p)
        start_x_p = tx + (area_texto_w - total_p_w) // 2
        
        draw.text((start_x_p, ty_b + 35), "S/ ", font=f_s, fill=BLANCO if es_efe else NEGRO)
        draw.text((start_x_p + draw.textlength("S/ ", font=f_s), ty_b + 10), p_val, font=f_p, fill=BLANCO if es_efe else NEGRO)
        
        sku_val = str(prod['%Cod Articulo'])
        draw.rounded_rectangle([tx, ty_b + 140, tx+area_texto_w, ty_b + 220], radius=35, fill=rec_color_s)
        draw.rectangle([tx, ty_b + 140, tx+area_texto_w, ty_b + 175], fill=rec_color_s)
        tw_sku = draw.textlength(sku_val, font=f_sku_prod)
        draw.text((tx + (area_texto_w - tw_sku)//2, ty_b + 150), sku_val, font=f_sku_prod, fill=BLANCO)

    return flyer

def procesar_tienda(nombre_tienda, grupo):
    print(f"Generando PDF: {nombre_tienda}")
    paginas = []
    grupo_priorizado = grupo.sort_values(by='es_top10', ascending=False)
    
    indices = grupo_priorizado.index.tolist()
    for i in range(0, len(indices), 6):
        bloque = grupo_priorizado.iloc[i:i+6].to_dict('records')
        img_f = crear_flyer(bloque, str(nombre_tienda), (i//6)+1)
        # Se dibuja a 2500x3750 y se reduce a PDF_ANCHO: el sitio de Pages pesa menos y despliega más rápido
        pagina = img_f.convert("RGB").resize((PDF_ANCHO, int(ALTO * PDF_ANCHO / ANCHO)), Image.Resampling.LANCZOS)
        img_f.close()
        paginas.append(pagina)
    
    if paginas:
        t_clean = "".join(x for x in str(nombre_tienda) if x.isalnum() or x in " -_")
        pdf_fn = f"PDF_{t_clean}.pdf"
        pdf_path = os.path.join(output_dir, pdf_fn)
        # quality=70 reduce el peso de los PDF: el sitio de Pages ya pesa ~724 MB y el límite es 1 GB
        paginas[0].save(pdf_path, save_all=True, append_images=paginas[1:], quality=PDF_QUALITY, optimize=True)
        for p in paginas: p.close()
        
        pdf_fn_encoded = urllib.parse.quote(pdf_fn)
        # ?v=fecha obliga al navegador a bajar la versión nueva y no la guardada en caché
        return [nombre_tienda, f"{URL_BASE_PAGES}{pdf_fn_encoded}?v={VERSION_LINK}"]
    return None

# --- FLUJO PRINCIPAL ---
ss = conectar_sheets()

print("Descargando datos y cruzando Top 10...")
df_source = pd.DataFrame(ss.worksheet("Sheetgo_Detalle de Inventario").get_all_records())
df_lookup = pd.DataFrame(ss.worksheet("listado_productos").get_all_records())

# CARGAR TOP 10 Y APLICAR LIMPIEZA DE SKU (-EX)
try:
    df_top10 = pd.DataFrame(ss.worksheet("Sheetgo_Top10 Obsoletos").get_all_records())
    df_top10['SKU'] = df_top10['SKU'].astype(str).str.replace('-EX', '', case=False).str.strip()
    
    print(f"Top 10 en el Sheet: {len(df_top10)} filas. Fechas leídas: {df_top10['Fin de vigencia'].astype(str).unique().tolist()[:5]}")
    df_top10['Fin de vigencia'] = df_top10['Fin de vigencia'].apply(parsear_fecha)
    if df_top10['Fin de vigencia'].isna().any():
        print(f"Aviso: {df_top10['Fin de vigencia'].isna().sum()} fechas de 'Fin de vigencia' no se pudieron leer.")
    hoy = ahora_peru.replace(hour=0, minute=0, second=0, microsecond=0)
    lista_skus_top = df_top10[df_top10['Fin de vigencia'] >= hoy]['SKU'].tolist()
    print(f"Top 10 vigentes cargados: {len(lista_skus_top)}")
except Exception as e:
    print(f"Aviso: Error procesando Top 10 ({e}).")
    lista_skus_top = []

df_source['%Cod Articulo'] = df_source['%Cod Articulo'].astype(str).str.replace('-EX', '', case=False).str.strip()
# Cruce SKU -> imagen, sin importar mayúsculas, espacios ni el sufijo -EX
df_lookup['sku_norm'] = normalizar_sku(df_lookup['sku'])
df_lookup['base_image_path'] = df_lookup['base_image_path'].astype(str).str.strip()
df_lookup = df_lookup[~df_lookup['base_image_path'].str.lower().isin(['', 'nan', 'none'])]
lookup_dict = df_lookup.drop_duplicates('sku_norm').set_index('sku_norm')['base_image_path'].to_dict()
df_source['image_link'] = normalizar_sku(df_source['%Cod Articulo']).map(lookup_dict).fillna('')
con_link = (df_source['image_link'] != '').sum()
print(f"listado_productos: {len(lookup_dict)} SKU con imagen. Productos del inventario con imagen asignada: {con_link}/{len(df_source)}")
if con_link < len(df_source):
    sin = df_source.loc[df_source['image_link'] == '', '%Cod Articulo'].unique()[:5].tolist()
    print(f"  Ejemplos de SKU sin imagen en listado_productos: {sin}")
precargar_imagenes(df_source['image_link'].tolist())

df_source['es_top10'] = df_source['%Cod Articulo'].isin(lista_skus_top)

# Actualizar hoja Detalle de Inventario
ws_detalle = ss.worksheet("Detalle de Inventario")
ws_detalle.clear()
ws_detalle.update(values=[df_source.columns.values.tolist()] + df_source.values.tolist(), range_name='A1')

# Generar PDFs
grupos = df_source.groupby('Tienda Retail')
tienda_links_pdf = []
with ThreadPoolExecutor(max_workers=2) as executor:
    futuros = [executor.submit(procesar_tienda, n, g) for n, g in grupos if str(n).strip()]
    for f in futuros:
        res = f.result()
        if res: tienda_links_pdf.append(res)

# REFUERZO: Pequeña pausa para no saturar la API antes del paso final
time.sleep(3)

# Actualizar Tabla Maestra
try:
    hoja_pdf = ss.worksheet("FLYER_TIENDA")
except:
    hoja_pdf = ss.add_worksheet(title="FLYER_TIENDA", rows="100", cols="2")

hoja_pdf.clear()
hoja_pdf.update(values=[["TIENDA RETAIL", "LINK PDF FLYERS"]] + tienda_links_pdf, range_name='A1')

# REFUERZO: Visibilidad de pestañas con Try-Except para evitar paros por Error 500
print("Configurando visibilidad de hojas...")
try:
    hojas_visibles = ["FLYER_TIENDA", "Sheetgo_Detalle de Inventario", "Sheetgo_Top10 Obsoletos"]
    requests_list = []
    for ws in ss.worksheets():
        requests_list.append({
            "updateSheetProperties": {
                "properties": {"sheetId": ws.id, "hidden": ws.title not in hojas_visibles},
                "fields": "hidden"
            }
        })
    ss.batch_update({"requests": requests_list})
except Exception as e:
    print(f"Aviso: No se pudo actualizar la visibilidad de las hojas ({e}), pero el proceso continuará.")

print("¡Proceso exitoso!")
