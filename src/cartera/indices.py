"""Compatibilidad de la API española; implementación en fixed-income-toolkit 0.2.0."""

from market_data.providers.bcra import (
    BCRAError as ErrorBCRA,
    RemSurvey as Rem,
    SERIES,
    URL,
    save_capture as _guardar,
    extract as extraer,
    read_rem as leer_rem,
)
from financial_engine._common import _mes, _precision, _distancia_meses, parse_bcra_date as _fecha
from financial_engine.indexed import (
    IndexedValue as Valor,
    _geometrica,
    _publicado,
    a3500_index as indice_a3500,
    cer_index as indice_cer,
    monthly_inflation as inflacion_mensual,
    project_capitalizing as proyectar_capitalizable,
    bcra_series as serie_bcra,
    daily_tamar as tamar_diaria,
    tamar_monthly_rate as tem_tamar,
)
