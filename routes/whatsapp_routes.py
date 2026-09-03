"""WhatsApp webhook handler for the Event Bot."""

import logging
import re
import datetime

from flask import Blueprint, request, abort

from utils import (
    parse_date_from_text,
    parse_time_from_text,
    get_spanish_day_name,
    LOCAL_TIMEZONE,
    get_timezone,
)
from services import TwilioService, FirestoreService, GeminiService
from models import Evento

logger = logging.getLogger(__name__)

whatsapp_blueprint = Blueprint("whatsapp", __name__)

# ── Injected dependencies (set by create_app) ─────────────────────────────────

# Services are injected by the app factory
twilio_service: Optional[TwilioService] = None
firestore_service: Optional[FirestoreService] = None
gemini_service: Optional[GeminiService] = None

# Conversation state - now stored in Firestore with TTL
# This replaces the old in-memory CONVERSATION_STATE
conversation_state: dict = {}  # Fallback; primary is Firestore


# ── Helper functions ──────────────────────────────────────────────────────────

def _validate_required_fields(form_data: dict, required: list[str]) -> Optional[str]:
    """Validate that required form fields are present. Returns error message or None."""
    missing = [field for field in required if not form_data.get(field)]
    if missing:
        logger.warning("Campos faltantes en webhook: %s", missing)
        return f"Faltan campos requeridos: {', '.join(missing)}"
    return None


def _send_error_response(resp, message: str) -> str:
    """Send an error message via WhatsApp and return the TwiML response."""
    resp.message(message)
    return str(resp)


# ── WhatsApp Webhook Route ─────────────────────────────────────────────────────

@whatsapp_blueprint.route("/whatsapp", methods=["POST"])
def whatsapp_reply():
    """Handle incoming WhatsApp messages."""
    # Validate required fields
    form = request.form
    error = _validate_required_fields(form, ["Body", "From"])
    if error:
        return _send_error_response(MessagingResponse(), error)

    msg = form.get("Body", "").strip()
    from_number = form.get("From", "").strip()
    resp = MessagingResponse()

    # --- Lógica para borrar un evento ---
    if msg.lower().startswith("borrar evento"):
        try:
            match = re.search(r'borrar evento\s+(\d+)', msg, re.IGNORECASE)
            if match:
                conteo_a_borrar = int(match.group(1))
                if firestore_service and firestore_service.delete_event_by_conteo(conteo_a_borrar):
                    resp.message(f"El evento número {conteo_a_borrar} ha sido borrado.")
                else:
                    resp.message(f"No se pudo borrar el evento número {conteo_a_borrar}. Quizás no existe o hubo un error.")
            else:
                resp.message("Formato no reconocido. Usa 'borrar evento [conteo]'.")
        except ValueError:
            resp.message("Formato no reconocido. Usa 'borrar evento [conteo]'.")
        except Exception as e:
            logger.error("Error al procesar el borrado del evento: %s", e, exc_info=True)
            resp.message("Hubo un error al procesar tu solicitud de borrado. Por favor, intenta de nuevo.")
        return str(resp)

    # --- Manejar la respuesta a un conflicto de horarios ---
    if from_number in conversation_state:
        state = conversation_state[from_number]

        try:
            choice = int(msg.strip())

            # Obtener datos del evento que causa el conflicto
            new_event_data = state['new_event_data']

            # Obtener los datos completos del evento en conflicto para verificar si es recurrente
            if firestore_service:
                conflicting_event_ref = firestore_service.db.collection("eventos").document(state['conflicting_event_id'])
                conflicting_event_data = conflicting_event_ref.get().to_dict()
                conflicting_event_is_recurring = conflicting_event_data.get("recurrente", False)
            else:
                conflicting_event_is_recurring = False

            if choice == 1:
                # Lógica de reemplazo (conservar el nuevo evento)
                if conflicting_event_is_recurring:
                    # Si es recurrente, solo insertamos el nuevo evento y dejamos el recurrente
                    if firestore_service and firestore_service.add_event(Evento(
                        evento=new_event_data['evento'],
                        dia=new_event_data['dia'],
                        fecha=new_event_data['fecha_str'] and datetime.datetime.strptime(new_event_data['fecha_str'], '%Y-%m-%d').date() if new_event_data['fecha_str'] else None,
                        hora=new_event_data['hora'],
                        recurrente=new_event_data['recurrente'],
                    )):
                        resp.message("¡El nuevo evento se ha guardado para esa fecha! El evento recurrente original se ha conservado para los demás días.")
                    else:
                        resp.message("Hubo un error al guardar el nuevo evento. Por favor, inténtalo de nuevo.")
                else:
                    # Si no es recurrente, borramos el antiguo y guardamos el nuevo
                    if firestore_service and firestore_service.delete_event_by_conteo(int(state['conflicting_event_id'])):
                        if firestore_service and firestore_service.add_event(Evento(
                            evento=new_event_data['evento'],
                            dia=new_event_data['dia'],
                            fecha=new_event_data['fecha_str'] and datetime.datetime.strptime(new_event_data['fecha_str'], '%Y-%m-%d').date() if new_event_data['fecha_str'] else None,
                            hora=new_event_data['hora'],
                            recurrente=new_event_data['recurrente'],
                        )):
                            resp.message("¡El nuevo evento se ha guardado y el antiguo ha sido eliminado!")
                        else:
                            resp.message("Hubo un error al guardar el nuevo evento. Por favor, inténtalo de nuevo.")
                    else:
                        resp.message("Hubo un error al eliminar el evento antiguo. Por favor, inténtalo de nuevo.")
            elif choice == 2:
                # Lógica para conservar el evento existente
                resp.message("Se ha conservado el evento original. El nuevo evento no se ha guardado.")
            else:
                resp.message("Opción no válida. Por favor, responde 1 o 2.")
                return str(resp)
        except ValueError:
            resp.message("Respuesta no válida. Por favor, responde con el número 1 o 2.")
            return str(resp)
        except Exception as e:
            logger.error("Error al procesar la respuesta al conflicto: %s", e, exc_info=True)
            resp.message("Hubo un error al procesar tu respuesta. Por favor, inténtalo de nuevo.")

        # Remove from conversation state (Firestore cleanup)
        if from_number in conversation_state:
            del conversation_state[from_number]
        # Also try to delete from Firestore
        if firestore_service:
            firestore_service.conversation_state_delete(from_number)

        return str(resp)

    # --- Lógica para agregar un nuevo evento ---
    if msg.lower().startswith("agregar evento"):
        try:
            # Split the command
            comando_parts_list = msg.lower().split('agregar evento', 1)

            if len(comando_parts_list) < 2 or not comando_parts_list[1].strip():
                resp.message("Por favor, proporciona los detalles del evento en formato 'agregar evento [día] a las [HH:MM] [descripción]'.")
                return str(resp)

            comando_parts = comando_parts_list[1].strip()

            match_time = re.search(r'a las |en ', comando_parts, re.IGNORECASE)

            if not match_time:
                resp.message("Formato no reconocido. Asegúrate de usar 'a las' o 'en' para indicar la hora.")
                return str(resp)

            dia_texto = comando_parts[:match_time.start()].strip()
            horario_y_descripcion = comando_parts[match_time.end():].strip()

            dia, fecha, fecha_fin, recurrente = parse_date_from_text(dia_texto)
            hora = parse_time_from_text(horario_y_descripcion)

            if not dia or not hora:
                resp.message("Formato de día u hora no reconocido. Asegúrate de usar una fecha (DD/MM/YYYY), un día de la semana, 'hoy' o 'mañana', seguido de la hora en formato 24 horas (HH:MM).")
                return str(resp)

            # Validate that the time format is correct
            try:
                datetime.datetime.strptime(hora, "%H:%M")
            except ValueError:
                resp.message("Formato de hora incorrecto. Por favor, usa HH:MM.")
                return str(resp)

            # Timezone-aware check for "hoy" events
            if fecha and fecha == datetime.date.today():
                try:
                    now_server = datetime.datetime.now()
                    now_local = now_server.astimezone(get_timezone())

                    evento_hoy_datetime = now_local.replace(
                        hour=int(hora.split(':')[0]),
                        minute=int(hora.split(':')[1]),
                        second=0,
                        microsecond=0,
                    )

                    if evento_hoy_datetime <= now_local:
                        resp.message("¡Error! No puedes agregar un evento para una hora que ya ha pasado hoy. Por favor, elige una hora futura.")
                        return str(resp)
                except ValueError:
                    resp.message("Formato de hora incorrecto. Por favor, usa HH:MM.")
                    return str(resp)

            # Extract event description
            descripcion_match = re.search(r'(\d{1,2}:\d{2})$', horario_y_descripcion)

            if descripcion_match:
                evento = horario_y_descripcion[:descripcion_match.start()].strip()
            else:
                evento = horario_y_descripcion.strip()

            if not evento:
                evento = "Evento sin descripción"

            # Check for conflicts
            eventos_del_dia = firestore_service.get_events_for_day_and_time(dia, fecha, hora) if firestore_service else []
            conflicto = len(eventos_del_dia) > 0

            if conflicto:
                conflicting_event_id, evento_conflicto, hora_conflicto, conflicting_is_recurring = eventos_del_dia[0]
                fecha_str_new = fecha.strftime('%Y-%m-%d') if fecha else None

                # Store in conversation state (both in-memory and Firestore)
                conversation_state[from_number] = {
                    'conflicting_event_id': conflicting_event_id,
                    'new_event_data': {
                        'evento': evento,
                        'dia': dia,
                        'fecha_str': fecha_str_new,
                        'hora': hora,
                        'recurrente': recurrente
                    }
                }
                # Also save to Firestore for persistence
                if firestore_service:
                    firestore_service.conversation_state_set(from_number, conversation_state[from_number])

                message_conflict = f"¡Atención! Hay un conflicto de horario. Ya tienes el evento '{evento_conflicto}' a las {hora_conflicto}.\n¿Qué quieres hacer?\n"

                if conflicting_is_recurring:
                    message_conflict += "1. Conservar el evento nuevo (solo para esta fecha)\n"
                else:
                    message_conflict += "1. Conservar el evento nuevo (eliminará el antiguo)\n"

                message_conflict += "2. Conservar el evento existente\nResponde con '1' o '2'."

                resp.message(message_conflict)
            else:
                fecha_fin_obj = None
                if fecha_fin:
                    fecha_fin_obj = fecha_fin

                # Create Evento model and add to Firestore
                nuevo_evento = Evento(
                    evento_texto=evento,
                    dia_semana=dia,
                    fecha=fecha,
                    hora=hora,
                    recurrente=recurrente,
                )

                if firestore_service and firestore_service.add_event(nuevo_evento):
                    if fecha_fin:
                        # Recurring event with end date
                        current_date = datetime.date.today()
                        day_index = list(_get_dia_semana_map().values()).index(dia)

                        while current_date.weekday() != day_index:
                            current_date += datetime.timedelta(days=1)

                        added_count = 0
                        while current_date <= fecha_fin_obj:
                            if firestore_service and firestore_service.add_event(Evento(
                                evento_texto=evento,
                                dia_semana=dia,
                                fecha=current_date,
                                hora=hora,
                                recurrente=False,
                            )):
                                added_count += 1
                            current_date += datetime.timedelta(days=7)

                        resp.message(f"¡Evento '{evento}' agregado para todos los {dia.lower()} hasta el {fecha_fin_obj.strftime('%d/%m/%Y')}!")
                    elif recurrente:
                        dia_espanol = get_spanish_day_name(dia)
                        resp.message(f"¡Evento '{evento}' agregado para todos los {dia_espanol.lower()} a las {hora}!")
                    else:
                        fecha_espanol_str = fecha.strftime('%d/%m/%Y') if fecha else ""
                        dia_espanol = get_spanish_day_name(dia)
                        resp.message(f"¡Evento '{evento}' agregado para el {dia_espanol} {fecha_espanol_str} a las {hora}!")
                else:
                    resp.message("Hubo un error al agregar el evento. Por favor, inténtalo de nuevo.")

        except (IndexError, ValueError, re.error) as e:
            logger.error("Error al procesar el mensaje: %s", e, exc_info=True)
            resp.message("Hubo un error al procesar el formato del mensaje. Asegúrate de usar un formato claro. Ejemplos: 'agregar evento hoy a las 10:00 reunión', 'agregar evento 26/08/2025 a las 12:00 arreglar la sala', o 'agregar evento todos los martes hasta el 26/08/2025 a las 9:00 clases en la U'")
        except Exception as e:
            logger.error("Error inesperado al procesar mensaje: %s", e, exc_info=True)
            resp.message("Hubo un error inesperado. Por favor, intenta de nuevo con un formato claro.")

    # --- Lógica para mostrar todos los eventos programados ---
    elif "mostrar eventos" in msg.lower():
        if firestore_service:
            eventos = firestore_service.get_all_events()
        else:
            eventos = []

        if eventos:
            MAX_MESSAGE_LENGTH = 1500

            # OBtener el tiempo actual con zona horaria
            ahora = datetime.datetime.now(get_timezone())

            eventos_con_proxima_fecha = []

            # Mapeo de días de la semana de inglés a español
            english_days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

            for id, data in eventos:
                if data.get("recurrente"):
                    # Calcular la próxima fecha para un evento recurrente
                    dia_semana_recurrente = data.get("dia_semana")

                    # Encontrar el índice del día de la semana actual
                    dia_semana_ahora = ahora.weekday() # Lunes es 0, Domingo es 6

                    # Encontrar el índice del día de la semana del evento
                    try:
                        dia_semana_evento = english_days.index(dia_semana_recurrente)
                    except ValueError:
                        continue # Si el día de la semana no es válido, pasamos al siguiente evento

                    # Calcular cuántos días faltan para el próximo evento
                    dias_a_sumar = dia_semana_evento - dia_semana_ahora

                    if dias_a_sumar < 0:
                        dias_a_sumar += 7

                    # Si el evento es hoy, revisamos la hora
                    hora_evento_str = data.get("hora")
                    try:
                        hora_evento = datetime.datetime.strptime(hora_evento_str, '%H:%M').time()
                    except ValueError:
                        continue # Si la hora no es válida, pasamos al siguiente evento

                    if dias_a_sumar == 0 and hora_evento < ahora.time():
                        dias_a_sumar += 7 # Pasamos a la siguiente semana

                    proxima_fecha = ahora + datetime.timedelta(days=dias_a_sumar)

                    # Establecer la hora del evento
                    proxima_fecha = proxima_fecha.replace(hour=hora_evento.hour, minute=hora_evento.minute, second=0, microsecond=0)

                    data["proxima_fecha"] = proxima_fecha
                    eventos_con_proxima_fecha.append((id, data))
                else:
                    # Calcular la próxima fecha para un evento no recurrente
                    fecha_evento_str = data.get("fecha")
                    hora_evento_str = data.get("hora")
                    try:
                        # 1. Crear el objeto datetime naive
                        naive_evento_datetime = datetime.datetime.strptime(f"{fecha_evento_str} {hora_evento_str}", '%Y-%m-%d %H:%M')
                        # 2. Asignarle la zona horaria para que sea 'aware'
                        evento_datetime = get_timezone().localize(naive_evento_datetime)
                    except (ValueError, pytz.NonExistentTimeError, pytz.AmbiguousTimeError):
                        continue # Si la fecha/hora no es válida o ambigua, pasamos al siguiente evento

                    if evento_datetime >= ahora:
                        data["proxima_fecha"] = evento_datetime
                        eventos_con_proxima_fecha.append((id, data))

            if eventos_con_proxima_fecha:
                # Ordenamos todos los eventos por la próxima fecha
                eventos_con_proxima_fecha.sort(key=lambda x: x[1].get('proxima_fecha'))

                # Inicializamos el primer mensaje
                mensaje_actual = "Aquí están tus eventos programados en orden cronológico:\n\n"

                # Recorremos cada evento para construir los mensajes
                for id, data in eventos_con_proxima_fecha:
                    evento, dia_semana, fecha, hora, recurrente, conteo = (
                        data["evento_texto"],
                        data["dia_semana"],
                        data.get("fecha"),
                        data["hora"],
                        data["recurrente"],
                        data["conteo"],
                    )

                    # Construimos la línea de texto para el evento actual
                    if recurrente:
                        dia_espanol = get_spanish_day_name(dia_semana)
                        linea_evento = f"• {conteo}: Todos los {dia_espanol.lower()} a las {hora}: {evento}\n"
                    else:
                        fecha_obj = datetime.datetime.strptime(fecha, '%Y-%m-%d')
                        dia_espanol = get_spanish_day_name(fecha_obj.strftime('%A'))
                        fecha_formateada = fecha_obj.strftime('%d/%m/%Y')
                        linea_evento = f"• {conteo}: {dia_espanol} {fecha_formateada} a las {hora}: {evento}\n"

                    # Verificamos si la línea actual excede el límite del mensaje
                    if len(mensaje_actual) + len(linea_evento) > MAX_MESSAGE_LENGTH:
                        # Si lo excede, enviamos el mensaje actual
                        resp.message(mensaje_actual)
                        # Y comenzamos un nuevo mensaje con la línea actual
                        mensaje_actual = linea_evento
                    else:
                        # Si no lo excede, añadimos la línea al mensaje actual
                        mensaje_actual += linea_evento

                # Enviamos el último mensaje restante
                if mensaje_actual.strip():
                    resp.message(mensaje_actual)
            else:
                # Si después del filtro no hay eventos, enviamos este mensaje
                mensaje = "No tienes eventos programados en este momento."
                resp.message(mensaje)
        else:
            # Si no hay eventos, enviamos un solo mensaje
            mensaje = "No tienes eventos programados en este momento."
            resp.message(mensaje)

    # --- Lógica para mostrar solo los eventos pendientes del día ---
    elif msg.lower().startswith("listar eventos para"):
        dia_texto = msg.lower().split("listar eventos para")[1].strip()
        if firestore_service:
            eventos = firestore_service.get_events_for_a_day(dia_texto)
        else:
            eventos = []

        if eventos:
            mensaje = f"Eventos programados para el {dia_texto.capitalize()}:\n"
            # Now use the conteo to show in the message
            for id, evento, hora, _, _, conteo in eventos:
                mensaje += f"{conteo}: {hora}: {evento}\n"
        else:
            mensaje = f"No tienes eventos programados para el {dia_texto.capitalize()}."
        resp.message(mensaje)

    elif "listar eventos" in msg.lower:
        if firestore_service:
            eventos = firestore_service.get_events_for_today()
        else:
            eventos = []

        now_local = datetime.datetime.now(get_timezone())
        hora_actual_obj = now_local.time()

        eventos_pendientes = []

        for id, evento, hora_db, conteo in eventos:
            try:
                hora_evento_obj = datetime.datetime.strptime(hora_db, '%H:%M').time()
            except ValueError:
                continue

            if hora_evento_obj >= hora_actual_obj:
                eventos_pendientes.append((id, evento, hora_db, conteo))

        dia_semana_actual_es = get_spanish_day_name(datetime.date.today().strftime('%A'))

        if eventos_pendientes:
            mensaje = f"Eventos pendientes para hoy ({dia_semana_actual_es}):\n"
            for id, evento, hora, conteo in eventos_pendientes:
                mensaje += f"{conteo}: {hora}: {evento}\n"
        else:
            mensaje = "No tienes eventos pendientes para hoy. ¡Disfruta el resto de tu día!"

        resp.message(mensaje)

    # --- 3. Respuesta predeterminada para otros comandos ---
    else:
        resp.message("Recibí tu mensaje, pero aún no sé cómo procesar ese comando. Intenta con 'agregar evento', 'listar eventos', 'mostrar eventos' o 'borrar evento'.")

    return str(resp)


# ── Health check for the blueprint ─────────────────────────────────────────────

@whatsapp_blueprint.route("/health", methods=["GET"])
def whatsapp_health():
    """WhatsApp blueprint health check."""
    return {"status": "ok", "message": "WhatsApp blueprint operativo"}, 200