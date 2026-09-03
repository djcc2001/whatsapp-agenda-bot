"""Data models for the WhatsApp Event Bot."""

from __future__ import annotations

from datetime import date, datetime, timedelta, time as TimeType


class Evento:
    """Represents a calendar event."""

    def __init__(
        self,
        evento_texto: str,
        dia_semana: str,
        fecha: date | None = None,
        hora: str | None = None,
        recurrente: bool = False,
        conteo: int | None = None,
    ):
        self.evento_texto = evento_texto
        self.dia_semana = dia_semana
        self.fecha = fecha
        self.hora = hora
        self.recurrente = recurrente
        self.conteo = conteo

    def to_dict(self) -> dict:
        return {
            "evento_texto": self.evento_texto,
            "dia_semana": self.dia_semana,
            "fecha": self.fecha.isoformat() if self.fecha else None,
            "hora": self.hora,
            "recurrente": self.recurrente,
            "conteo": self.conteo,
        }

    @staticmethod
    def from_dict(data: dict) -> Evento:
        return Evento(
            evento_texto=data.get("evento_texto", ""),
            dia_semana=data.get("dia_semana", ""),
            fecha=datetime.strptime(data["fecha"], "%Y-%m-%d").date() if data.get("fecha") else None,
            hora=data.get("hora"),
            recurrente=data.get("recurrente", False),
            conteo=data.get("conteo"),
        )


class Recordatorio:
    """Represents a reminder associated with an event."""

    def __init__(self, evento_texto: str, hora_evento: str, minutos_antes: int = 15):
        self.evento_texto = evento_texto
        self.hora_evento = hora_evento
        self.minutos_antes = minutos_antes

    def calcular_hora_recordatorio(self) -> datetime:
        hora_obj = datetime.strptime(self.hora_evento, "%H:%M")
        return datetime.combine(datetime.now().date(), hora_obj.time()) - timedelta(minutes=self.minutos_antes)

    def to_dict(self) -> dict:
        return {
            "evento_texto": self.evento_texto,
            "hora_evento": self.hora_evento,
            "minutos_antes": self.minutos_antes,
        }


class ConflictResolution:
    """Represents a user's conflict resolution choice."""

    DEFER = "defer"
    REPLACE = "replace"
    KEEP_EXISTING = "keep_existing"

    def __init__(self, choice: str, from_number: str, new_event_data: dict | None = None, conflicting_event_id: str | None = None):
        self.choice = choice
        self.from_number = from_number
        self.new_event_data = new_event_data or {}
        self.conflicting_event_id = conflicting_event_id