"""Utility functions for the WhatsApp Event Bot."""

import os
import re
import datetime
import logging
from datetime import date, datetime, timedelta
from typing import Optional, Tuple

import pytz

# Centralized timezone configuration
# Default to America/Lima, but can be overridden via environment variable
LOCAL_TIMEZONE_NAME = os.environ.get("LOCAL_TIMEZONE", "America/Lima")
LOCAL_TIMEZONE = pytz.timezone(LOCAL_TIMEZONE_NAME)

logger = logging.getLogger(__name__)


def get_timezone() -> pytz.BaseTzInfo:
    """Return the configured local timezone object."""
    return LOCAL_TIMEZONE


def parse_date_from_text(text: str) -> Tuple[Optional[str], Optional[date], Optional[date], bool]:
    """
    Parse day and date from user text.
    Returns: (day_name_en, fecha_obj, fecha_fin_obj, recurrente)
    """
    text_lower = text.lower()

    # 1. Check for recurring event with end date: "todos los [día] hasta el DD/MM/YYYY"
    match_recurrente_hasta = re.search(r'todos los (\w+) hasta el (\d{1,2}/\d{1,2}/\d{4})', text_lower)

    if match_recurrente_hasta:
        dia_es = match_recurrente_hasta.group(1)
        fecha_fin_str = match_recurrente_hasta.group(2)

        try:
            dia_en = _dia_semana_es_para_en(dia_es)
            fecha_fin_obj = datetime.strptime(fecha_fin_str, "%d/%m/%Y").date()

            if dia_en:
                return dia_en, None, fecha_fin_obj, True
        except ValueError:
            return None, None, None, False

    # 2. Check for indefinite recurring event: "todos los [día]"
    for dia_es, dia_en in _get_dia_semana_map().items():
        if f'todos los {dia_es}' in text_lower:
            return dia_en, None, None, True

    # 3. Check for specific date (DD/MM/YYYY)
    date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', text)

    if date_match:
        date_str = date_match.group(1)

        try:
            date_obj = datetime.strptime(date_str, "%d/%m/%Y").date()
            day_name_en = date_obj.strftime("%A")
            return day_name_en, date_obj, None, False
        except ValueError:
            return None, None, None, False

    # 4. Check for "hoy" or "mañana"
    if "hoy" in text_lower:
        today = date.today()
        return today.strftime("%A"), today, None, False
    elif "mañana" in text_lower:
        tomorrow = date.today() + timedelta(days=1)
        return tomorrow.strftime("%A"), tomorrow, None, False

    # 5. Check for "el siguiente/próximo [día]" or just the day name
    today = date.today()
    current_day_index = today.weekday()
    dias_semana = _get_dia_semana_map()

    for dia_es, dia_en in dias_semana.items():
        if (f"el siguiente {dia_es}" in text_lower or f"el proximo {dia_es}" in text_lower or text_lower == dia_es):
            target_day_index = list(dias_semana.keys()).index(dia_es)
            days_until_next = (target_day_index - current_day_index + 7) % 7

            if days_until_next == 0:
                days_until_next = 7
            next_date = today + timedelta(days=days_until_next)

            return next_date.strftime("%A"), next_date, None, False

    return None, None, None, False


def parse_time_from_text(text: str) -> Optional[str]:
    """Extract time in 24h format (HH:MM) from text."""
    match = re.search(r'(\d{1,2}:\d{2})', text)

    if match:
        hora_str = match.group(1)

        try:
            datetime.strptime(hora_str, "%H:%M")
            return hora_str
        except ValueError:
            return None

    return None


def get_spanish_day_name(english_day: str) -> str:
    """Convert an English day name to Spanish."""
    dias_semana = _get_dia_semana_map()

    for dia_es, dia_en in dias_semana.items():
        if dia_en.lower() == english_day.lower():
            return dia_es.capitalize()

    return english_day


def _dia_semana_es_para_en(dia_es: str) -> Optional[str]:
    """Convert Spanish day name to English (reverse mapping helper)."""
    mapa = _get_dia_semana_map()
    # The original map has Spanish keys -> English values
    return mapa.get(dia_es.lower())


def _get_dia_semana_map() -> dict[str, str]:
    """Return the Spanish-to-English day mapping."""
    return {
        "lunes": "Monday",
        "martes": "Tuesday",
        "miércoles": "Wednesday",
        "jueves": "Thursday",
        "viernes": "Friday",
        "sábado": "Saturday",
        "domingo": "Sunday",
    }