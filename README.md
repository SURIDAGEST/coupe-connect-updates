# Coupé Connect — instaladores Android

Sistema multimedia propio para radio Android y teléfono. **Prototipo de desarrollo:** la proyección todavía requiere prueba física; faltan navegación guiada y reconexión de vídeo automática.

## Instalación nueva y prueba del actualizador

El cambio de firma requiere desinstalar las versiones antiguas una sola vez. Si hay registros que conservar, exportar una copia antes de desinstalar.

1. Instalar [Car 0.6.2 en la radio](https://github.com/SURIDAGEST/coupe-connect-updates/releases/download/v2026.11.21-car8-phone7/car-8-c336c06d77aa0fa0d440c00e4dfa2b484154f10fad127466fbd65b8164abacec.apk) y [Móvil 0.5.2 en el teléfono](https://github.com/SURIDAGEST/coupe-connect-updates/releases/download/v2026.11.21-car8-phone7/phone-7-8ecc730cf3a7698d7bfbad9871b344508b1c7d48226d1c5de3da24c01cc1855b.apk).
2. Abrir cada app → Actualizaciones → Buscar → Descargar → Instalar. El canal ofrece Car 0.6.3 y Móvil 0.5.3. Android pedirá los permisos y confirmaciones que correspondan.
3. Las actualizaciones siguientes usan el canal ya configurado y la misma firma. No necesitan desinstalar ni trasladar APK manualmente.

La conservación de datos y la instalación real están pendientes de comprobación en dispositivos. El incremento final de versión permite probar el canal; conserva las funciones de la versión anterior.

## Últimas versiones directamente

- [Coupé Connect Car 0.6.3](https://github.com/SURIDAGEST/coupe-connect-updates/releases/download/v2026.11.21-car9-phone8/car-9-90717264f3d06491742f2f4ce926a5f734e622f7f4bfbde333a98ae87c7cc4e1.apk) — radio Android. Escritorio local y receptor de proyección.
- [Coupé Connect Móvil 0.5.3](https://github.com/SURIDAGEST/coupe-connect-updates/releases/download/v2026.11.21-car9-phone8/phone-8-02de322ce1c6f0c2140a9af64143c14869c1e7004d1b38f2d9917c5f1e65ee7b.apk) — teléfono Android. Mi garaje y emisor de proyección.

## Proyección experimental

Conectar ambos a la misma Wi-Fi. Radio: Ajustes → Recibir proyección del móvil. Móvil: ficha del vehículo → Proyectar → Escanear QR → Autorizar controles de Spotify → Iniciar. Spotify se reproduce en el móvil; el audio depende del Bluetooth del sistema. El mapa tiene ubicación y zoom, todavía sin rutas guiadas.

## Integridad

Canales: [car.json](https://github.com/SURIDAGEST/coupe-connect-updates/releases/latest/download/car.json) y [phone.json](https://github.com/SURIDAGEST/coupe-connect-updates/releases/latest/download/phone.json). Las apps realizan consultas frescas para evitar caché de redirecciones. Verifican el manifiesto firmado, tamaño, SHA-256, paquete, versión y firma del instalador.

Certificado de distribución SHA-256: `a6bccb1011d8a6baa4b5a79dee6f250aca35dd08d5da78eb4267c09da96e53b9`.

Este repositorio distribuye únicamente instaladores y metadatos públicos. No contiene claves privadas, datos de garaje ni credenciales de edición.
