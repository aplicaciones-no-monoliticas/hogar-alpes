# Actividades por integrante — DOC-3

Enlaza cada bloque de `docs/03-tareas.md` con los commits y PR que lo
implementaron. Convención de trabajo del proyecto (§0 de `03-tareas.md`): una
rama por bloque, un PR por bloque, **desde la cuenta de quien lo hace** — es
lo que hace verificable la contribución equitativa que pide el enunciado (R-1).

Repositorio: `aplicaciones-no-monoliticas/hogar-alpes`.

---

## Andrés Gómez

| Bloque | Tareas | PR | Commit(s) |
|---|---|---|---|
| Fundaciones e infraestructura | INF-0…6, CON-1 | [#2](../../pull/2) [#3](../../pull/3) [#4](../../pull/4) [#5](../../pull/5) [#6](../../pull/6) | `84ad288` `d96ad36` `ed09fad` `b2f6d45` `4b51a91` `26c612b` `43df16b` |
| `gestion_trabajos` — procesos y despachador (GT-1, GT-2) | GT-1, GT-2 | [#8](../../pull/8) | `2bfdb3f` |
| Sistema completo desde un clon limpio | INT-1, INF-5 | [#10](../../pull/10) | `61aed07` |
| Stream unificado | GT-3 | [#11](../../pull/11) | `2a9646a` |
| Cierre de Gestión de Trabajos, escenarios de modificabilidad y esquemas, AWS, README | GT-4, GT-5, GT-6, GT-7, ESC-M, ESC-E, DEP-1, DOC-1 | rama `andres/gt-ajustes-finales` — **pendiente de PR desde su cuenta** | `25a1099` `6daaa02` `281944c` `dcc7068` `16e257a` (preparados en esta sesión; a revisar y volver a subir por Andrés antes de fusionar) |

## Stiven Cardona

| Bloque | Tareas | PR | Commit(s) |
|---|---|---|---|
| Servicio `operaciones`, generador de carga, escenario 6, Postman | OPS-1…4, HER-1, ESC-6, INT-2 | [#9](../../pull/9) | `f783cef` |
| Cierre de escenario 6 tras GT-3 | Simplificación de `escenario-6.sh` y `generador_carga.py` | rama `stiven/cierre-escenario-6` | (esta sesión) |

## Juan Manuel Domínguez

| Bloque | Tareas | PR | Commit(s) |
|---|---|---|---|
| Acreditación y Emparejamiento | ACR-1…5, EMP-1…5 | [#7](../../pull/7) | `e54852d` `a4bac89` |
| Herramientas de medición y escenario 8 | HER-2, HER-3, ESC-8 | [#7](../../pull/7) | `04f219c` `7bdc6ff` |

---

## Lo que queda por correr, no por escribir

Varias tareas anteriores (ESC-6, ESC-8, ESC-M, ESC-E, DEP-1, DEP-2) tienen su
código y sus scripts listos pero su **corrida formal contra un clúster real
o contra AWS** pendiente — el detalle exacto está en `docs/03-tareas.md` y en
`docs/decisiones.md`. No es trabajo sin asignar: es trabajo que necesita
Docker (o, para DEP-1/DEP-2, credenciales de AWS) que no estaban disponibles
en el entorno donde se escribió.
