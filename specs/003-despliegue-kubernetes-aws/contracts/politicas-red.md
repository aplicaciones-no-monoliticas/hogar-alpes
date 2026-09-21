# Contrato: verificación de aislamiento de red (FR-008 a FR-011, CA-3.11 a CA-3.14)

Este contrato define cómo cualquier implementación debe **demostrar**, no solo declarar, el
aislamiento de red — es el criterio más importante de la historia (R5-12).

## Las nueve comprobaciones de aislamiento por base de datos (repetidas de la Entrega 4)

Desde dentro de un pod de cada uno de los servicios de dominio (`gestion-trabajos`,
`operaciones`, `acreditacion`, `emparejamiento`), intentar una conexión TCP directa (`nc -zv` o
equivalente ya usado en el guion de Compose) contra el puerto 5432 de cada una de las bases de
datos **que no es la suya**. Con 5 bases y 4 servicios de dominio que no deberían alcanzar la
base de otro, y `saga_log` que tampoco debería, la matriz reproduce las mismas nueve
combinaciones prohibidas ya enumeradas en el guion equivalente de Compose.

**Resultado esperado**: las nueve conexiones fallan por timeout/rechazo (no por error de DNS —
eso probaría que ni siquiera se intentó la conexión real, no que la política la bloqueó).

## Las comprobaciones de aislamiento HTTP entre servicios de dominio

Desde dentro de un pod de cada servicio de dominio, intentar un `curl` HTTP contra el `Service`
de cada uno de los otros servicios de dominio (nunca contra el BFF, que sí debe poder alcanzarlos
a todos).

**Resultado esperado**: la conexión falla (rechazada por la `NetworkPolicy`, no por error 404/500
de la aplicación — un 404 significaría que la conexión de red sí pasó).

## Comprobación positiva (control)

Desde dentro del pod del BFF, `curl` contra el `/health` de cada uno de los seis servicios.

**Resultado esperado**: las seis responden 200 — confirma que la política no está bloqueando de
más (falso positivo de aislamiento) y que el problema real que se prueba es específico a
servicio-a-servicio, no una `NetworkPolicy` rota que bloquea todo.

## Comprobación de exposición externa

Desde una máquina fuera del clúster (el mismo runner que corre el guion, sin acceso privilegiado
al VPC), intentar alcanzar: el puerto 5432 de cualquier base, el puerto del broker de Pulsar
(6650/8080), y comparar contra alcanzar el `Service` `LoadBalancer` del BFF.

**Resultado esperado**: todo excepto el BFF falla o ni siquiera resuelve (sin IP pública/
`LoadBalancer` asignado); el BFF responde.

## Formato del resultado

Igual que todos los guiones de escenario existentes (Principio VI de la constitución): cada
comprobación se reporta como PASA o FALLA en `docs/resultados/`, releyendo el resultado real del
intento de conexión (código de salida de `nc`/`curl`), nunca infiriéndolo de que la política
"se aplicó sin error" en `kubectl apply`.
