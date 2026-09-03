"""Service integrations for the WhatsApp Event Bot."""

import json
import logging
from typing import Optional

import firebase_admin
from firebase_admin import credentials, firestore
from google.genai import Client

from models import Evento

logger = logging.getLogger(__name__)


# ── Twilio Service ────────────────────────────────────────────────────────────

class TwilioService:
    """Handles Twilio SMS/WhatsApp operations."""

    def __init__(self, account_sid: str, auth_token: str, whatsapp_number: str):
        from twilio.rest import Client
        self.client = Client(account_sid, auth_token)
        self.whatsapp_number = whatsapp_number

    def send_message(self, to: str, body: str) -> None:
        """Send a WhatsApp message."""
        try:
            message = self.client.messages.create(
                from_=self.whatsapp_number,
                body=body,
                to=to,
            )
            logger.info("Mensaje enviado con éxito: %s", message.sid)
        except Exception as e:
            logger.error("Error al enviar mensaje: %s", e, exc_info=True)
            raise


# ── Firestore Service ─────────────────────────────────────────────────────────

class FirestoreService:
    """Handles Firebase Firestore operations."""

    def __init__(self, db):
        self.db = db

    def get_events_for_today(self) -> list:
        """Get all events for today."""
        if not self.db:
            return []

        from datetime import date as DateType
        today = DateType.today()
        today_str = today.strftime("%Y-%m-%d")
        today_en = today.strftime("%A")

        one_off_events = []
        recurring_events = []

        # Unique events for today
        docs = self.db.collection("eventos").where("fecha", "==", today_str).stream()
        one_off_events = [
            (doc.id, doc.to_dict()["evento_texto"], doc.to_dict()["hora"], doc.to_dict().get("conteo"))
            for doc in docs
        ]

        # Hours of unique events to filter recurring
        one_off_hours = {event[2] for event in one_off_events}

        # Recurring events for today
        docs = self.db.collection("eventos").where("dia_semana", "==", today_en).where("recurrente", "==", True).stream()
        all_recurring_events = [
            (doc.id, doc.to_dict()["evento_texto"], doc.to_dict()["hora"], doc.to_dict().get("conteo"))
            for doc in docs
        ]

        # Filter recurring events that conflict with unique events
        recurring_events = [event for event in all_recurring_events if event[2] not in one_off_hours]
        all_events = one_off_events + recurring_events

        return sorted(all_events, key=lambda x: x[2])

    def get_events_for_a_day(self, dia_texto: str) -> list:
        """Get events for a specific day of the week."""
        if not self.db:
            return []

        from datetime import date as DateType

        today = DateType.today()
        current_day_index = today.weekday()
        dia_es = dia_texto.lower()
        dia_en = self._get_dia_en(dia_es)

        if not dia_en:
            return []

        target_day_index = list(self._get_dia_semana_map().keys()).index(dia_en)
        days_until_target = (target_day_index - current_day_index + 7) % 7
        target_date = today + __import__("datetime").timedelta(days=days_until_target)
        target_date_str = target_date.strftime("%Y-%m-%d")
        one_off_events = []
        recurring_events = []

        # Unique events for the target day
        docs = self.db.collection("eventos").where("fecha", "==", target_date_str).stream()
        one_off_events = [
            (doc.id, doc.to_dict()["evento_texto"], doc.to_dict()["hora"], doc.to_dict().get("fecha"), doc.to_dict().get("recurrente"), doc.to_dict().get("conteo"))
            for doc in docs
        ]

        # Hours of unique events to filter recurring
        one_off_hours = {event[2] for event in one_off_events}

        # Recurring events for the target day
        docs = self.db.collection("eventos").where("dia_semana", "==", dia_en).where("recurrente", "==", True).stream()
        all_recurring_events = [
            (doc.id, doc.to_dict()["evento_texto"], doc.to_dict()["hora"], doc.to_dict().get("fecha"), doc.to_dict().get("recurrente"), doc.to_dict().get("conteo"))
            for doc in docs
        ]

        # Filter recurring events that conflict with unique events
        recurring_events = [event for event in all_recurring_events if event[2] not in one_off_hours]
        all_events = one_off_events + recurring_events

        return sorted(all_events, key=lambda x: x[2])

    def _get_dia_en(self, dia_es: str) -> Optional[str]:
        """Convert Spanish day name to English."""
        mapa = self._get_dia_semana_map()
        return mapa.get(dia_es)

    def _get_dia_semana_map(self) -> dict[str, str]:
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

    def add_event(self, evento: Evento) -> str | None:
        """Add an event to Firestore. Returns the document ID."""
        if not self.db:
            logger.error("Firestore no inicializada")
            return None

        try:
            # Get next conteo
            next_conteo = 1
            docs = self.db.collection("eventos").order_by("conteo", direction=firebase_admin.firestore.Query.DESCENDING).limit(1).stream()
            for doc in docs:
                next_conteo = (doc.to_dict().get("conteo", 0) or 0) + 1

            self.db.collection("eventos").add({
                "evento_texto": evento.evento_texto,
                "dia_semana": evento.dia_semana,
                "fecha": evento.fecha.isoformat() if evento.fecha else None,
                "hora": evento.hora,
                "recurrente": evento.recurrente,
                "conteo": next_conteo,
            })
            logger.info("Evento agregado con conteo %s", next_conteo)
            return str(next_conteo)
        except Exception as e:
            logger.error("Error al insertar evento en Firestore: %s", e, exc_info=True)
            return None

    def delete_event_by_conteo(self, conteo: int) -> bool:
        """Delete an event from Firestore by its conteo number."""
        if not self.db:
            logger.error("Firestore no inicializada")
            return False

        try:
            docs = self.db.collection("eventos").where("conteo", "==", conteo).stream()

            for doc_to_delete in docs:
                self.db.collection("eventos").document(doc_to_delete.id).delete()
                logger.info("Evento %s eliminado", conteo)
                return True

            logger.warning("No se encontró evento con conteo %s", conteo)
            return False
        except Exception as e:
            logger.error("Error al eliminar evento en Firestore: %s", e, exc_info=True)
            return False

    def get_all_events(self) -> list:
        """Get all events from Firestore."""
        if not self.db:
            return []

        try:
            docs = self.db.collection("eventos").stream()
            return [(doc.id, doc.to_dict()) for doc in docs]
        except Exception as e:
            logger.error("Error al obtener todos los eventos: %s", e, exc_info=True)
            return []

    def get_events_for_day_and_time(self, dia_semana: str, fecha: object, hora: str) -> list:
        """Get events matching a specific day, date, and time for conflict detection."""
        if not self.db:
            return []

        conflicts = []
        if fecha:
            # Conflict in specific date (unique event)
            docs = self.db.collection("eventos").where("fecha", "==", fecha.strftime("%Y-%m-%d")).where("hora", "==", hora).stream()
            conflicts.extend([(doc.id, doc.to_dict()["evento_texto"], doc.to_dict()["hora"], doc.to_dict().get("recurrente", False)) for doc in docs])

            # Conflict with recurring event on that day
            docs = self.db.collection("eventos").where("dia_semana", "==", dia_semana).where("recurrente", "==", True).where("hora", "==", hora).stream()
            conflicts.extend([(doc.id, doc.to_dict()["evento_texto"], doc.to_dict()["hora"], doc.to_dict().get("recurrente", False)) for doc in docs])
        else:
            # Conflict in day of week for recurring events
            docs = self.db.collection("eventos").where("dia_semana", "==", dia_semana).where("hora", "==", hora).stream()
            conflicts.extend([(doc.id, doc.to_dict()["evento_texto"], doc.to_dict()["hora"], doc.to_dict().get("recurrente", False)) for doc in docs])

        return conflicts

    def conversation_state_get(self, from_number: str) -> dict | None:
        """Get conversation state for a user from Firestore."""
        if not self.db:
            return None

        try:
            doc = self.db.collection("conversation_state").document(from_number).get()
            if doc.exists:
                return doc.to_dict()
            return None
        except Exception as e:
            logger.error("Error al obtener estado de conversación: %s", e, exc_info=True)
            return None

    def conversation_state_set(self, from_number: str, state: dict) -> None:
        """Set conversation state for a user in Firestore with TTL."""
        if not self.db:
            return

        try:
            self.db.collection("conversation_state").document(from_number).set(state)
            # Set TTL expiration - expire after 24 hours
            expires_at = datetime.datetime.now() + datetime.timedelta(hours=24)
            self.db.collection("conversation_state").document(from_number).update({"expires_at": expires_at})
            logger.info("Estado de conversación guardado para %s", from_number)
        except Exception as e:
            logger.error("Error al guardar estado de conversación: %s", e, exc_info=True)

    def conversation_state_delete(self, from_number: str) -> None:
        """Delete conversation state for a user."""
        if not self.db:
            return

        try:
            self.db.collection("conversation_state").document(from_number).delete()
            logger.info("Estado de conversación eliminado para %s", from_number)
        except Exception as e:
            logger.error("Error al eliminar estado de conversación: %s", e, exc_info=True)


# ── Gemini Service ────────────────────────────────────────────────────────────

class GeminiService:
    """Handles Google Gemini AI operations using the new google-genai library."""

    def __init__(self, api_key: str):
        self.client = Client(api_key=api_key)
        self.model_name = "gemini-1.5-flash"

    def extract_command(self, user_text: str) -> Optional[dict]:
        """
        Use Gemini to extract command and parameters from user text.
        Returns dict with parsed command or None if extraction fails.
        """
        try:
            prompt = (
                "Extrae los siguientes datos del mensaje del usuario para un bot de agenda de eventos WhatsApp:\n"
                "- comando: 'agregar', 'listar', 'mostrar', 'borrar'\n"
                "- dia: nombre de día, fecha u 'hoy'/'mañana'\n"
                "- hora: formato HH:MM\n"
                "- descripcion: texto descriptivo del evento\n"
                "- recurrente: booleano si es recurrente\n\n"
                "Responde SOLO con un JSON válido con las claves arriba. Si no hay suficientes datos, indica 'insufficient_data'.\n\n"
                f"Mensaje: '{user_text}'"
            )
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
            )
            result = response.text.strip()

            # Try to parse JSON from the response
            import json as json_mod
            # Clean up possible markdown code block formatting
            if result.startswith("```"):
                result = result.split("```")[1]
                if result.startswith("json"):
                    result = result[5:].strip()

            parsed = json_mod.loads(result)
            return parsed
        except (json_mod.JSONDecodeError, Exception) as e:
            logger.warning("No se pudo extraer comando con Gemini: %s", e)
            return None