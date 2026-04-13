# PRUEBAS

Este apartado describe el proceso de validación del sistema de inventario, ventas y análisis inteligente desarrollado para La Séptima Estrella. La validación se realizó con pruebas automatizadas y verificaciones técnicas complementarias, con el fin de comprobar que el sistema cumple con los requisitos funcionales y no funcionales definidos para la solución.

La evidencia técnica de la ejecución quedó almacenada en los siguientes artefactos:

- [pytest-results.xml](/mnt/c/Users/User/Documents/septima%20estrella1/analisis-ventas-ia/artifacts/tests/pytest-results.xml)
- [pytest-summary.json](/mnt/c/Users/User/Documents/septima%20estrella1/analisis-ventas-ia/artifacts/tests/pytest-summary.json)
- [compileall.txt](/mnt/c/Users/User/Documents/septima%20estrella1/analisis-ventas-ia/artifacts/tests/compileall.txt)
- [frontend-check.txt](/mnt/c/Users/User/Documents/septima%20estrella1/analisis-ventas-ia/artifacts/tests/frontend-check.txt)

## Planificación de las pruebas

Antes de ejecutar las pruebas, se definió el alcance, los objetivos, los recursos técnicos y los criterios de aceptación. Se estableció como objetivo principal verificar el comportamiento correcto del sistema en los módulos de autenticación, usuarios, roles, productos, inventario, ventas, reportes, exportaciones, auditoría, respaldos e inteligencia artificial.

Se trabajó bajo las siguientes condiciones previas:

- El sistema se encontraba disponible en el entorno local del proyecto y podía ejecutarse desde el entorno virtual `.venv-linux`.
- Los datos de prueba ya estaban definidos dentro de la batería automatizada, mediante dobles de prueba, catálogos simulados, usuarios de diferentes roles y ventas de ejemplo.
- El entorno de pruebas fue controlado, ya que la validación se ejecutó sobre el repositorio local y con salidas registradas en artefactos verificables.
- Para cada caso se contaba con un resultado esperado explícito, definido en las aserciones de la suite de pruebas.

El alcance de la validación se organizó así:

| Tipo de prueba | Alcance principal | Herramienta | Criterio de aceptación |
| --- | --- | --- | --- |
| Funcional | Login, sesiones, usuarios, roles, productos, inventario, ventas, reportes, auditoría, IA, respaldos | `pytest` | El caso debe finalizar sin error y cumplir las aserciones previstas |
| Integración de backend | Endpoints Flask, serialización, exportes, permisos, transacciones y recuperación ante fallos | `pytest` | La respuesta, el estado y los datos devueltos deben coincidir con el resultado esperado |
| Verificación técnica de código | Compilación del código Python y sintaxis del frontend | `compileall` y `node --check` | No deben aparecer errores de compilación ni errores de sintaxis |

Los recursos utilizados en la ejecución fueron:

- Sistema operativo del entorno de prueba: entorno local controlado del proyecto.
- Host reportado por la suite automatizada: `PC-CESAR`.
- Fecha de ejecución principal: `2026-04-10T15:34:21-05:00`.
- Intérprete de pruebas: `.venv-linux/bin/python`.
- Evidencia estructurada: archivo JUnit XML y resumen JSON.

## Ejecución de las pruebas

Las pruebas se ejecutaron mediante los siguientes comandos:

```bash
.venv-linux/bin/python -m pytest -q --capture=no --junitxml=artifacts/tests/pytest-results.xml
.venv-linux/bin/python -m compileall src tests scripts > artifacts/tests/compileall.txt 2>&1
node --check src/frontend/app.js > artifacts/tests/frontend-check.txt 2>&1
```

La corrida principal automatizada registró:

- Total de casos ejecutados: `106`
- Casos exitosos: `106`
- Casos fallidos: `0`
- Casos con error: `0`
- Casos omitidos: `0`
- Tiempo total de la suite: `42.173 s`

### Tabla de resultados por módulo validado

| Archivo de prueba | Módulo o requisito validado | Casos ejecutados | Resultado obtenido | Estado |
| --- | --- | ---: | --- | --- |
| `tests/test_ai_reports.py` | Reportes IA, pronóstico de demanda, validación de entradas e imágenes de productos en pronóstico | 9 | Todos los casos finalizaron correctamente | Exitosa |
| `tests/test_audit_endpoints.py` | Consulta y exportación de auditoría, mezcla de eventos actuales y legado | 6 | Todos los casos finalizaron correctamente | Exitosa |
| `tests/test_chat_ai.py` | Respuestas del asistente IA para inventario, combos y saludos | 5 | Todos los casos finalizaron correctamente | Exitosa |
| `tests/test_config_roles_endpoints.py` | Configuración de IVA global y gestión de roles | 4 | Todos los casos finalizaron correctamente | Exitosa |
| `tests/test_data_paths.py` | Resolución de rutas de datos y archivos CSV de ventas | 1 | El caso finalizó correctamente | Exitosa |
| `tests/test_demo_generator.py` | Generación de datos demo reproducibles para evaluación | 2 | Todos los casos finalizaron correctamente | Exitosa |
| `tests/test_frontend_cache_busting.py` | Inyección correcta de versiones de assets frontend | 1 | El caso finalizó correctamente | Exitosa |
| `tests/test_ia_endpoints_auth.py` | Autenticación y permisos de endpoints IA | 5 | Todos los casos finalizaron correctamente | Exitosa |
| `tests/test_operations_improvements.py` | Bloqueo por intentos fallidos, migraciones, respaldos, exportación e importación de inventario e indicadores operativos | 14 | Todos los casos finalizaron correctamente | Exitosa |
| `tests/test_password_hashing.py` | Seguridad de contraseñas con PBKDF2 y compatibilidad con hashes previos | 3 | Todos los casos finalizaron correctamente | Exitosa |
| `tests/test_permissions_exports.py` | Permisos por rol, reportes, exportes PDF/Excel y dashboard de métodos de pago | 8 | Todos los casos finalizaron correctamente | Exitosa |
| `tests/test_registrar_venta.py` | Registro básico de venta | 1 | El caso finalizó correctamente | Exitosa |
| `tests/test_sale_voiding.py` | Anulación de ventas y restauración de stock | 8 | Todos los casos finalizaron correctamente | Exitosa |
| `tests/test_sales_flows.py` | Flujo transaccional de ventas, IVA global e individual, detalle de venta y movimientos de inventario | 12 | Todos los casos finalizaron correctamente | Exitosa |
| `tests/test_sessions.py` | Limpieza de sesiones, sesión vigente y cierre al reinicio del servidor | 6 | Todos los casos finalizaron correctamente | Exitosa |
| `tests/test_state_routes_audit.py` | Cambio de estado de productos y usuarios con registro en auditoría | 2 | Todos los casos finalizaron correctamente | Exitosa |
| `tests/test_users_roles.py` | Normalización de roles, permisos por defecto y CLI de usuarios base | 7 | Todos los casos finalizaron correctamente | Exitosa |
| `tests/test_validations.py` | Validaciones numéricas y normalización de payloads | 12 | Todos los casos finalizaron correctamente | Exitosa |

### Escenarios representativos documentados

La tabla siguiente resume escenarios concretos ejecutados durante la validación. Cada escenario corresponde a casos automatizados efectivamente corridos en la suite.

| Tipo de prueba | Módulo evaluado | Escenario ejecutado | Resultado esperado | Resultado obtenido | Estado |
| --- | --- | --- | --- | --- | --- |
| Funcional | Login | Bloquear acceso después de múltiples intentos fallidos consecutivos | El sistema debe responder con restricción temporal y tiempo restante | El bloqueo temporal se aplicó correctamente y el caso `test_login_rate_limit_blocks_after_repeated_failures` finalizó de forma satisfactoria | Exitosa |
| Funcional | Sesiones | Invalidar sesión previa al reiniciar el servidor | La sesión anterior no debe seguir vigente | La sesión fue invalidada correctamente en `test_current_user_clears_stale_session_after_server_restart` | Exitosa |
| Funcional | IVA global | Consultar y actualizar el IVA del sistema | El valor debe leerse y persistirse correctamente | La operación fue validada en `test_iva_config_get_and_put_work` | Exitosa |
| Funcional | Roles | Crear un rol personalizado desde el endpoint correspondiente | El rol debe almacenarse con permisos válidos | La creación se validó correctamente en `test_roles_endpoint_creates_custom_role` | Exitosa |
| Funcional | Productos | Exportar inventario en formato PDF | El archivo debe generarse sin error y con el nombre esperado | La exportación se validó en `test_inventory_export_endpoint_returns_pdf` | Exitosa |
| Funcional | Inventario | Detectar productos por debajo o muy cerca del mínimo | El dashboard debe incluir alertas de seguimiento | El comportamiento fue validado en `test_product_needs_stock_alert_includes_near_minimum_follow_up` | Exitosa |
| Funcional | Ventas | Rechazar ventas con cambio de precio no autorizado | La venta debe rechazarse sin alterar la integridad del sistema | El escenario se validó en `test_sale_rejected_when_price_change_exceeds_without_force` | Exitosa |
| Funcional | Ventas | Registrar venta con IVA específico por producto | El cálculo debe priorizar el IVA individual del producto | El comportamiento se validó en `test_sale_prefers_product_specific_iva_rate` | Exitosa |
| Funcional | Ventas | Revertir una transacción cuando ocurre un fallo intermedio | La operación debe hacer rollback y no dejar datos inconsistentes | La reversión se comprobó en `test_sale_rolls_back_on_db_failure` | Exitosa |
| Funcional | Anulación de ventas | Anular una venta y restaurar stock | El stock y el estado de la venta deben actualizarse correctamente | El caso `test_seller_can_disable_authorized_sale_and_restore_stock` finalizó correctamente | Exitosa |
| Funcional | Reportes | Exportar reporte de ventas en PDF | El archivo debe generarse con el nombre esperado | La salida fue verificada en `test_report_export_endpoint_returns_pdf` | Exitosa |
| Funcional | Auditoría | Consultar auditoría combinando eventos actuales y legacy | El endpoint debe devolver eventos consolidados y filtrables | El escenario fue validado en `test_audit_endpoint_merges_current_and_legacy_entries` | Exitosa |
| Funcional | IA | Generar pronóstico de demanda con respuesta estructurada | El endpoint debe devolver riesgo, cobertura y compra sugerida | La respuesta fue validada en `test_ia_forecast_endpoint_returns_payload` | Exitosa |
| Funcional | IA | Incluir la imagen del producto en la respuesta del pronóstico | El payload debe entregar la URL o data URL utilizable | El comportamiento se validó en `test_ia_forecast_includes_product_image_urls` | Exitosa |
| Seguridad | Autorización | Restringir endpoints de IA a usuarios autenticados o autorizados | El acceso debe negarse cuando el rol no cumple la política | Los casos `test_ia_chat_requires_login` y `test_ia_forecast_requires_admin_role` finalizaron correctamente | Exitosa |

### Verificaciones técnicas complementarias

| Verificación | Herramienta | Resultado esperado | Resultado obtenido | Estado |
| --- | --- | --- | --- | --- |
| Compilación del backend y la batería de pruebas | `python -m compileall` | No deben aparecer errores de compilación | La compilación finalizó sin errores y quedó registrada en `artifacts/tests/compileall.txt` | Exitosa |
| Revisión sintáctica del frontend | `node --check src/frontend/app.js` | No debe existir error de sintaxis en el JavaScript principal | La validación terminó sin errores y quedó registrada en `artifacts/tests/frontend-check.txt` | Exitosa |

## Análisis de resultados

Una vez ejecutadas las pruebas, se comparó el resultado esperado de cada caso con el comportamiento real del sistema. El análisis muestra que la solución se comportó de forma satisfactoria en los módulos funcionales críticos y en las verificaciones técnicas complementarias.

Los resultados permitieron establecer que:

- El sistema respondió correctamente en autenticación, sesiones, usuarios, roles y control de permisos.
- Los módulos de productos, inventario y ventas se comportaron de forma consistente, incluyendo escenarios de IVA global, IVA individual por producto, movimientos de stock y rollback transaccional.
- Los procesos de auditoría, respaldos y exportaciones funcionaron conforme a lo esperado.
- El módulo de inteligencia artificial respondió correctamente tanto en consultas conversacionales como en pronóstico de demanda y restricciones por rol.
- No se presentaron fallas activas en la corrida ejecutada.

Durante la ejecución aparecieron mensajes de consola en algunos escenarios controlados. Estas salidas no corresponden a defectos vigentes del sistema, sino a fallos simulados o condiciones intencionalmente provocadas por los dobles de prueba para verificar recuperación, rollback, control de sesiones y manejo de errores. La evidencia principal es que todos esos casos finalizaron en estado satisfactorio dentro de la suite.

En cuanto al tiempo de ejecución, la suite completa finalizó en `42.173 s`. El caso más costoso fue `test_ia_forecast_endpoint_without_sales`, con `19.090 s`, y finalizó correctamente. El resto de los casos presentó tiempos bajos de ejecución, lo cual indica estabilidad razonable para el entorno de validación utilizado.

## Resultados generales de las pruebas

En total se ejecutaron `106` casos automatizados de prueba, de los cuales:

- `106` fueron exitosos.
- `0` presentaron fallas.
- `0` presentaron errores.
- `0` fueron omitidos.

Adicionalmente, se ejecutaron `2` verificaciones técnicas complementarias:

- Compilación integral del backend y de la batería de pruebas.
- Revisión sintáctica del frontend principal.

Ambas verificaciones finalizaron correctamente.

## Conclusiones de las pruebas

Con base en los resultados obtenidos, se concluye que el sistema se encuentra en condiciones técnicas de ser utilizado en un entorno real controlado, ya que cumplió satisfactoriamente con los requisitos funcionales y de soporte evaluados durante la validación.

La evidencia obtenida muestra que el sistema:

- Gestiona correctamente autenticación, sesiones y permisos.
- Mantiene integridad en ventas, inventario y cálculos de IVA.
- Genera respaldos, reportes y exportaciones de manera consistente.
- Conserva trazabilidad mediante auditoría.
- Integra un módulo de IA funcional y controlado por permisos.

No obstante, se recomienda complementar esta validación con pruebas adicionales de carga, pruebas de aceptación con usuarios reales del negocio y mediciones operativas en el contexto productivo del establecimiento, con el fin de fortalecer la evaluación del desempeño bajo uso continuo y condiciones reales de operación.
