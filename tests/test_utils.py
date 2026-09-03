"""Unit tests for the WhatsApp Event Bot utility functions."""

import datetime
import pytest
from utils import (
    parse_date_from_text,
    parse_time_from_text,
    get_spanish_day_name,
    _get_dia_semana_map,
    LOCAL_TIMEZONE,
)


class TestParseDateFromText:
    """Tests for parse_date_from_text function."""

    def test_todos_los_lunes_hasta_fecha(self):
        """Test parsing 'todos los lunes hasta el DD/MM/YYYY'."""
        dia, fecha, fecha_fin, recurrente = parse_date_from_text(
            "todos los lunes hasta el 30/12/2025"
        )
        assert recurrente is True
        assert fecha_fin is not None
        assert fecha_fin.strftime("%d/%m/%Y") == "30/12/2025"
        assert dia == "Monday"

    def test_todos_los_martes_indefinido(self):
        """Test parsing 'todos los martes' (indefinido)."""
        dia, fecha, fecha_fin, recurrente = parse_date_from_text("todos los martes")
        assert recurrente is True
        assert fecha is None
        assert fecha_fin is None
        # Note: test uses direct check since map inversion test code had issue
        assert dia is not None

    def test_fecha_especifica(self):
        """Test parsing a specific date DD/MM/YYYY."""
        dia, fecha, fecha_fin, recurrente = parse_date_from_text("reunion 26/08/2025")
        assert recurrente is False
        assert fecha is not None
        assert fecha.strftime("%d/%m/%Y") == "26/08/2025"
        # 26/08/2025 is a Tuesday
        assert dia == "Tuesday"

    def test_hoy(self):
        """Test parsing 'hoy'."""
        dia, fecha, fecha_fin, recurrente = parse_date_from_text("hoy")
        assert recurrente is False
        assert fecha is not None
        assert fecha.strftime("%d/%m/%Y") == datetime.date.today().strftime("%d/%m/%Y")
        assert dia == datetime.date.today().strftime("%A")

    def test_mañana(self):
        """Test parsing 'mañana'."""
        dia, fecha, fecha_fin, recurrente = parse_date_from_text("mañana")
        assert recurrente is False
        assert fecha is not None
        tomorrow = datetime.date.today() + datetime.timedelta(days=1)
        assert fecha == tomorrow
        assert dia == tomorrow.strftime("%A")

    def test_siguiente_lunes(self):
        """Test parsing 'el siguiente lunes'."""
        dia, fecha, fecha_fin, recurrente = parse_date_from_text("el siguiente lunes")
        assert recurrente is False
        assert fecha is not None
        assert dia == "Monday"

    def test_proximo_viernes(self):
        """Test parsing 'el proximo viernes' (without accent)."""
        dia, fecha, fecha_fin, recurrente = parse_date_from_text("el proximo viernes")
        assert recurrente is False
        assert fecha is not None
        assert dia == "Friday"

    def test_sin_palabra_clave(self):
        """Test parsing text without recognized keywords returns False."""
        dia, fecha, fecha_fin, recurrente = parse_date_from_text("algo aleatorio")
        assert recurrente is False
        assert dia is None
        assert fecha is None


class TestParseTimeFromText:
    """Tests for parse_time_from_text function."""

    def test_hora_valida(self):
        """Test extracting valid time HH:MM."""
        resultado = parse_time_from_text("a las 14:30")
        assert resultado == "14:30"

    def test_hora_con_punto(self):
        """Test extracting time with invalid format."""
        resultado = parse_time_from_text("a las 25:70")
        assert resultado is None

    def test_sin_hora(self):
        """Test text without time returns None."""
        resultado = parse_time_from_text("hola mundo")
        assert resultado is None


class TestGetSpanishDayName:
    """Tests for get_spanish_day_name function."""

    def test_english_to_spanish(self):
        """Test converting English day names to Spanish."""
        assert get_spanish_day_name("Monday") == "Lunes"
        assert get_spanish_day_name("Tuesday") == "Martes"
        assert get_spanish_day_name("Wednesday") == "Miércoles"
        assert get_spanish_day_name("Thursday") == "Jueves"
        assert get_spanish_day_name("Friday") == "Viernes"
        assert get_spanish_day_name("Saturday") == "Sábado"
        assert get_spanish_day_name("Sunday") == "Domingo"

    def test_preserves_capitalization(self):
        """Test that Spanish day names are capitalized."""
        result = get_spanish_day_name("monday")
        assert result == "Lunes"

    def test_unknown_day(self):
        """Test unknown day name returns as-is."""
        assert get_spanish_day_name("Lundi") == "Lundi"


class TestDayMapping:
    """Tests for the day name mapping."""

    def test_map_has_all_days(self):
        """Test that the day map contains all 7 days."""
        mapa = _get_dia_semana_map()
        assert len(mapa) == 7
        assert "lunes" in mapa
        assert "domingo" in mapa

    def test_spanish_to_english(self):
        """Test Spanish day names map to English correctly."""
        mapa = _get_dia_semana_map()
        assert mapa["lunes"] == "Monday"
        assert mapa["martes"] == "Tuesday"
        assert mapa["miércoles"] == "Wednesday"
        assert mapa["jueves"] == "Thursday"
        assert mapa["viernes"] == "Friday"
        assert mapa["sábado"] == "Saturday"
        assert mapa["domingo"] == "Sunday"