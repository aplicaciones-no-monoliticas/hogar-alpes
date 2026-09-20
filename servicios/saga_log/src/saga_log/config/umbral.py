"""D9 de research.md: `INCOMPLETA` no se calcula al vuelo en el consumidor —
es una consulta que compara `iniciada_en` contra este umbral sobre las filas
todavía en `EN_CURSO`/`COMPENSANDO`. Configurable, generoso por defecto: muy
por encima de la latencia de punta a punta esperada."""
import os


def umbral_incompleta_segundos() -> int:
    return int(os.getenv('UMBRAL_INCOMPLETA_SEGUNDOS', '60'))
