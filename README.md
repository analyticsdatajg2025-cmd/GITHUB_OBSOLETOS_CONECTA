# GITHUB_OBSOLETOS_CONECTA
Creación de catálogo de imágenes para cada tienda y marca (LC y EFE)

## Resumen para MKT SISTEMA
- El script anota la ejecución en `resumen.json` (`resumen.py`): tiendas OK/error, productos por tienda,
  link del PDF, imágenes faltantes y si la data está al día (Top 10 con vigencia hasta hoy o después).
- El paso «Publicar resumen para MKT SISTEMA» lo sube al release `resumenes` como
  `obsoletos_<run_id>_0.json`. MKT SISTEMA (módulo «Lento y Obsoletos») lo lee y lo guarda 30 días.
  Los archivos de más de 5 días se borran solos del release. Este paso nunca hace fallar el job.
