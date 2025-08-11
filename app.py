import os
import re
import datetime
import google.generativeai as genai
from flask import Flask, request
from twilio.rest import Client
from apscheduler.schedulers.background import BackgroundScheduler
from twilio.twiml.messaging_response import MessagingResponse
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, firestore
import json
import pytz

# Cargar variables de entorno del archivo .env
load_dotenv()
  
app = Flask(__name__)

ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.environ.get("TWILIO_WHATSAPP_NUMBER")
YOUR_PHONE_NUMBER = os.environ.get("YOUR_PHONE_NUMBER")
 
client = Client(ACCOUNT_SID, AUTH_TOKEN)  

# Tu clave de API de Google Gemini
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)
  
# Inicializa Firebase
# Para el despliegue, la clave JSON se lee de una variable de entorno.
firebase_json_key = os.environ.get("FIREBASE_SERVICE_ACCOUNT_KEY")

if firebase_json_key:

    try:
        cred_json = json.loads(firebase_json_key)
        cred = credentials.Certificate(cred_json)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("Firebase inicializado correctamente.")
    except Exception as e:
        print(f"Error al inicializar Firebase: {e}")
        db = None

else:
    print("Error: La variable de entorno 'FIREBASE_SERVICE_ACCOUNT_KEY' no está configurada.")
    db = None

LOCAL_TIMEZONE = pytz.timezone('America/Lima')

# Estado de la conversación para manejar conflictos, se borra al reiniciar
CONVERSATION_STATE = {}
 
# Mapeo de días de la semana en español a inglés para datetime
DIA_SEMANA_MAP = {
    'lunes': 'Monday',
    'martes': 'Tuesday',
    'miércoles': 'Wednesday',
    'jueves': 'Thursday',
    'viernes': 'Friday',
    'sábado': 'Saturday',
    'domingo': 'Sunday'
}
 
def get_next_conteo():
    """Obtiene el siguiente número de conteo para un nuevo evento."""
    if not db:
        return 1
    try:
        docs = db.collection("eventos").order_by("conteo", direction=firestore.Query.DESCENDING).limit(1).stream()

        for doc in docs:
            return doc.to_dict().get("conteo", 0) + 1
        
        return 1
    except Exception as e:
        print(f"Error al obtener el siguiente conteo: {e}")
        return 1
 
def insert_event(evento_texto, dia_semana, fecha, hora, recurrente):
    """Inserta un nuevo evento en Firebase."""
    if not db:
        print("Error: La base de datos no está inicializada.")
        return False
    
    try:
        next_conteo = get_next_conteo()
        db.collection("eventos").add({
            "evento_texto": evento_texto,
            "dia_semana": dia_semana,
            "fecha": fecha.strftime('%Y-%m-%d') if fecha else None,
            "hora": hora,
            "recurrente": recurrente,
            "conteo": next_conteo  # Agregamos el campo 'conteo'
        })
        return True
    except Exception as e:
        print(f"Error al insertar evento en Firestore: {e}")
        return False
 
def delete_event_by_conteo(conteo):
    """Elimina un evento de Firebase por su número de conteo."""
    if not db:
        print("Error: La base de datos no está inicializada.")
        return False
    
    try:
        # Buscamos el documento que coincida con el número de conteo
        docs = db.collection("eventos").where("conteo", "==", conteo).stream()

        for doc_to_delete in docs:
            db.collection("eventos").document(doc_to_delete.id).delete()
            return True
        
        return False  # No se encontró el evento con ese conteo
    except Exception as e:
        print(f"Error al eliminar evento en Firestore: {e}")
        return False
 
def get_day_from_text(text):
    """Extrae el día y la fecha de un texto."""
    text_lower = text.lower()
 
    # 1. Comprobar si es un evento recurrente con fecha de finalización
    match_recurrente_hasta = re.search(r'todos los (\w+) hasta el (\d{1,2}/\d{1,2}/\d{4})', text_lower)

    if match_recurrente_hasta:
        dia_es = match_recurrente_hasta.group(1)
        fecha_fin_str = match_recurrente_hasta.group(2)

        try:
            dia_en = DIA_SEMANA_MAP.get(dia_es)
            fecha_fin_obj = datetime.datetime.strptime(fecha_fin_str, '%d/%m/%Y').date()

            if dia_en:
                return dia_en, None, fecha_fin_obj, True
            
        except ValueError:
            return None, None, None, False
 
    # 2. Comprobar si es un evento recurrente indefinido ("todos los [día]")
    for dia_es, dia_en in DIA_SEMANA_MAP.items():
        if f'todos los {dia_es}' in text_lower:
            return dia_en, None, None, True
 
    # 3. Comprobar si es una fecha específica (DD/MM/YYYY)
    date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', text)

    if date_match:
        date_str = date_match.group(1)

        try:
            date_obj = datetime.datetime.strptime(date_str, '%d/%m/%Y').date()
            day_name_en = date_obj.strftime('%A')
            return day_name_en, date_obj, None, False
        except ValueError:
            return None, None, None, False
 
    # 4. Comprobar si es "hoy" o "mañana"
    if 'hoy' in text_lower:
        return datetime.date.today().strftime('%A'), datetime.date.today(), None, False
    elif 'mañana' in text_lower:
        tomorrow = datetime.date.today() + datetime.timedelta(days=1)
        return tomorrow.strftime('%A'), tomorrow, None, False
 
    today = datetime.date.today()
    current_day_index = today.weekday()
 
    # 5. Comprobar si es "el siguiente/próximo [día]" o solo el día de la semana
    for dia_es, dia_en in DIA_SEMANA_MAP.items():
        if (f'el siguiente {dia_es}' in text_lower or f'el proximo {dia_es}' in text_lower or text_lower == dia_es):
            target_day_index = list(DIA_SEMANA_MAP.keys()).index(dia_es)
            days_until_next = (target_day_index - current_day_index + 7) % 7

            if days_until_next == 0:
                days_until_next = 7
            next_date = today + datetime.timedelta(days=days_until_next)

            return next_date.strftime('%A'), next_date, None, False
        
    return None, None, None, False
  
def get_time_from_text(text):
    """Extrae la hora en formato 24h (HH:MM) de un texto."""
    match = re.search(r'(\d{1,2}:\d{2})', text)

    if match:
        hora_str = match.group(1)

        try:
            datetime.datetime.strptime(hora_str, '%H:%M')
            return hora_str
        except ValueError:
            return None

    return None
  
def get_spanish_day_name(english_day):
    """Convierte el nombre de un día de la semana de inglés a español."""

    for dia_es, dia_en in DIA_SEMANA_MAP.items():
        if dia_en == english_day:
            return dia_es.capitalize()

    return english_day
  
def send_whatsapp_message(to, body):
    """Función para enviar un mensaje de WhatsApp."""
    try:
        message = client.messages.create(
            from_=TWILIO_WHATSAPP_NUMBER,
            body=body,
            to=to
        )
        print(f"Mensaje enviado con éxito: {message.sid}")
    except Exception as e:
        print(f"Error al enviar el mensaje: {e}")
  
def get_events_for_today():
    """Obtiene todos los eventos para el día de hoy, tanto recurrentes como únicos,
    priorizando los únicos en caso de conflicto."""
    if not db:
        return []

    today = datetime.date.today()
    today_en = today.strftime('%A')
    today_str = today.strftime('%Y-%m-%d')
    one_off_events = []
    recurring_events = []
  
    # Eventos únicos para hoy
    docs = db.collection("eventos").where("fecha", "==", today_str).stream()
    one_off_events = [(doc.id, doc.to_dict()["evento_texto"], doc.to_dict()["hora"], doc.to_dict()["conteo"]) for doc in docs]
  
    # Obtener las horas de los eventos únicos para filtrar los recurrentes
    one_off_hours = {event[2] for event in one_off_events}
 
    # Eventos recurrentes para hoy
    docs = db.collection("eventos").where("dia_semana", "==", today_en).where("recurrente", "==", True).stream()
    all_recurring_events = [(doc.id, doc.to_dict()["evento_texto"], doc.to_dict()["hora"], doc.to_dict()["conteo"]) for doc in docs]
  
    # Filtrar los eventos recurrentes que tienen conflicto con eventos únicos
    recurring_events = [event for event in all_recurring_events if event[2] not in one_off_hours]
    all_events = one_off_events + recurring_events

    return sorted(all_events, key=lambda x: x[2])
  
def get_events_for_a_day(dia_texto):
    """Obtiene los eventos para un día de la semana específico, tanto únicos como recurrentes,
    priorizando los únicos en caso de conflicto."""
    if not db:
        return []

    today = datetime.date.today()
    current_day_index = today.weekday()
    dia_es = dia_texto.lower()
    dia_en = DIA_SEMANA_MAP.get(dia_es)

    if not dia_en:
        return []
  
    target_day_index = list(DIA_SEMANA_MAP.keys()).index(dia_es)
    days_until_target = (target_day_index - current_day_index + 7) % 7
    target_date = today + datetime.timedelta(days=days_until_target)
    target_date_str = target_date.strftime('%Y-%m-%d')
    one_off_events = []
    recurring_events = []
  
    # Eventos únicos para el día objetivo
    docs = db.collection("eventos").where("fecha", "==", target_date_str).stream()
    one_off_events = [(doc.id, doc.to_dict()["evento_texto"], doc.to_dict()["hora"], doc.to_dict()["fecha"], doc.to_dict()["recurrente"], doc.to_dict()["conteo"]) for doc in docs]
  
    # Obtener las horas de los eventos únicos para filtrar los recurrentes
    one_off_hours = {event[2] for event in one_off_events}
  
    # Eventos recurrentes para el día objetivo
    docs = db.collection("eventos").where("dia_semana", "==", dia_en).where("recurrente", "==", True).stream()
    all_recurring_events = [(doc.id, doc.to_dict()["evento_texto"], doc.to_dict()["hora"], doc.to_dict()["fecha"], doc.to_dict()["recurrente"], doc.to_dict()["conteo"]) for doc in docs]
  
    # Filtrar los eventos recurrentes que tienen conflicto con eventos únicos
    recurring_events = [event for event in all_recurring_events if event[2] not in one_off_hours]
    all_events = one_off_events + recurring_events

    return sorted(all_events, key=lambda x: x[2])
  
def get_all_events():
    """Obtiene todos los eventos de Firebase."""
    if not db:
        return []

    try:
        docs = db.collection("eventos").stream()
        return [(doc.id, doc.to_dict()) for doc in docs]
    except Exception as e:
        print(f"Error al obtener todos los eventos: {e}")
        return []
  
def get_events_for_day_and_time(dia_semana, fecha, hora):
    """Obtiene eventos que coinciden con un día, fecha y hora específicos para detección de conflictos."""
    if not db:
        return []

    conflicts = []
    if fecha:
        # Buscar conflicto en la fecha específica (evento único)
        docs = db.collection("eventos").where("fecha", "==", fecha.strftime('%Y-%m-%d')).where("hora", "==", hora).stream()
        conflicts.extend([(doc.id, doc.to_dict()["evento_texto"], doc.to_dict()["hora"], doc.to_dict()["recurrente"]) for doc in docs])

        # Buscar conflicto con un evento recurrente en ese mismo día
        docs = db.collection("eventos").where("dia_semana", "==", dia_semana).where("recurrente", "==", True).where("hora", "==", hora).stream()
        conflicts.extend([(doc.id, doc.to_dict()["evento_texto"], doc.to_dict()["hora"], doc.to_dict()["recurrente"]) for doc in docs])
    else:
        # Buscar conflicto en el día de la semana para eventos recurrentes
        docs = db.collection("eventos").where("dia_semana", "==", dia_semana).where("hora", "==", hora).stream()
        conflicts.extend([(doc.id, doc.to_dict()["evento_texto"], doc.to_dict()["hora"], doc.to_dict()["recurrente"]) for doc in docs])
  
    return conflicts
  
def daily_routine_message():
    """Genera y envía el mensaje de rutina matutina con ejemplos de comandos."""
    eventos = get_events_for_today()
    dia_semana_actual_es = get_spanish_day_name(datetime.date.today().strftime('%A'))
  
    if eventos:
        mensaje = f"¡Buenos días! Tu rutina para hoy ({dia_semana_actual_es}) es:\n"

        for id, evento, hora, conteo in eventos:
            mensaje += f"• {conteo}: {hora}: {evento}\n"

    else:
        mensaje = f"¡Buenos días! No tienes eventos programados para hoy ({dia_semana_actual_es})."
  
    send_whatsapp_message(YOUR_PHONE_NUMBER, mensaje)
  
def schedule_reminders():
    """Programa los recordatorios para los eventos del día."""
    eventos = get_events_for_today()
    ahora = datetime.datetime.now()
  
    for id, evento, hora_db, conteo in eventos:
        try:
            hora_evento_obj = datetime.datetime.strptime(hora_db, '%H:%M')
        except ValueError:
            continue

        hora_recordatorio = hora_evento_obj - datetime.timedelta(minutes=15)
        fecha_recordatorio = datetime.datetime.combine(ahora.date(), hora_recordatorio.time())

        if fecha_recordatorio > ahora:
            scheduler.add_job(
                send_whatsapp_message, 
                'date', 
                run_date=fecha_recordatorio, 
                args=[YOUR_PHONE_NUMBER, f"Recordatorio: Tienes '{evento}' en 15 minutos."]
            )
  
@app.route("/whatsapp", methods=['POST'])
def whatsapp_reply():
    """Maneja los mensajes entrantes de WhatsApp."""
    msg = request.form.get('Body')
    from_number = request.form.get('From')
    resp = MessagingResponse()
 
    if not db:
        resp.message("Error interno del servidor. La base de datos no está inicializada.")
        return str(resp)
  
    # --- Lógica para borrar un evento ---
    if msg.lower().startswith("borrar evento"):
        try:
            # Ahora busca un número de conteo
            match = re.search(r'borrar evento\s+(\d+)', msg, re.IGNORECASE)
            if match:
                conteo_a_borrar = int(match.group(1))
                if delete_event_by_conteo(conteo_a_borrar):
                    resp.message(f"El evento número {conteo_a_borrar} ha sido borrado.")
                else:
                    resp.message(f"No se pudo borrar el evento número {conteo_a_borrar}. Quizás no existe o hubo un error.")
            else:
                resp.message("Formato no reconocido. Usa 'borrar evento [conteo]'.")
        except Exception as e:
            print(f"Error al procesar el borrado del evento: {e}")
            resp.message("Hubo un error al procesar tu solicitud de borrado. Por favor, intenta de nuevo.")
        return str(resp)
  
    # --- Manejar la respuesta a un conflicto de horarios ---
    if from_number in CONVERSATION_STATE:
        state = CONVERSATION_STATE[from_number]
 
        try:
            choice = int(msg.strip())
 
            # Obtener datos del evento que causa el conflicto
            new_event_data = state['new_event_data']
 
            # Obtener los datos completos del evento en conflicto para verificar si es recurrente
            conflicting_event_ref = db.collection("eventos").document(state['conflicting_event_id'])
            conflicting_event_data = conflicting_event_ref.get().to_dict()
            conflicting_event_is_recurring = conflicting_event_data.get("recurrente", False)
 
            if choice == 1:
                # Lógica de reemplazo (conservar el nuevo evento)
                if conflicting_event_is_recurring:
                    # Si es recurrente, solo insertamos el nuevo evento y dejamos el recurrente
                    if insert_event(new_event_data['evento'], new_event_data['dia'], datetime.datetime.strptime(new_event_data['fecha_str'], '%Y-%m-%d') if new_event_data['fecha_str'] else None, new_event_data['hora'], new_event_data['recurrente']):
                        resp.message(f"¡El nuevo evento se ha guardado para esa fecha! El evento recurrente original se ha conservado para los demás días.")
                    else:
                        resp.message("Hubo un error al guardar el nuevo evento. Por favor, inténtalo de nuevo.")
                else:
                    # Si no es recurrente, borramos el antiguo y guardamos el nuevo
                    if db.collection("eventos").document(state['conflicting_event_id']).delete(): # No usamos la funcion delete_event_by_conteo porque aqui ya tenemos el ID directo de Firestore
                        if insert_event(new_event_data['evento'], new_event_data['dia'], datetime.datetime.strptime(new_event_data['fecha_str'], '%Y-%m-%d') if new_event_data['fecha_str'] else None, new_event_data['hora'], new_event_data['recurrente']):
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
            print(f"Error al procesar la respuesta al conflicto: {e}")
            resp.message("Hubo un error al procesar tu respuesta. Por favor, inténtalo de nuevo.")
 
        del CONVERSATION_STATE[from_number]
        return str(resp)
  
    # --- Lógica para agregar un nuevo evento ---
    if msg.lower().startswith("agregar evento"):
        comando_parts_list = msg.lower().split('agregar evento', 1)
 
        if len(comando_parts_list) < 2 or not comando_parts_list[1].strip():
            resp.message("Por favor, proporciona los detalles del evento en formato 'agregar evento [día] a las [HH:MM] [descripción]'.")
            return str(resp)
  
        comando_parts = comando_parts_list[1].strip()
 
        try:
            match_time = re.search(r'a las |en ', comando_parts, re.IGNORECASE)
 
            if not match_time:
                resp.message("Formato no reconocido. Asegúrate de usar 'a las' o 'en' para indicar la hora.")
                return str(resp)
  
            dia_texto = comando_parts[:match_time.start()].strip()
            horario_y_descripcion = comando_parts[match_time.end():].strip()
            dia, fecha, fecha_fin, recurrente = get_day_from_text(dia_texto)
            hora = get_time_from_text(horario_y_descripcion)
  
            if not dia or not hora:
                resp.message("Formato de día u hora no reconocido. Asegúrate de usar una fecha (DD/MM/YYYY), un día de la semana, 'hoy' o 'mañana', seguido de la hora en formato 24 horas (HH:MM).")
                return str(resp)
  
            if fecha and fecha == datetime.date.today():
                try:
                    # 1. Obtiene la hora actual del servidor (en su zona horaria, por ejemplo UTC)
                    now_server = datetime.datetime.now()
                    # 2. Convierte la hora del servidor a tu zona horaria local.
                    now_local = now_server.astimezone(LOCAL_TIMEZONE)

                    # 3. Crea el objeto datetime del evento usando tu hora local.
                    evento_hoy_datetime = now_local.replace(
                        hour=int(hora.split(':')[0]), 
                        minute=int(hora.split(':')[1]), 
                        second=0, 
                        microsecond=0
                    )

                    # 4. Compara el evento (en tu zona horaria) con la hora local actual.
                    if evento_hoy_datetime <= now_local:
                        resp.message("¡Error! No puedes agregar un evento para una hora que ya ha pasado hoy. Por favor, elige una hora futura.")
                        return str(resp)
                except ValueError:
                    resp.message("Formato de hora incorrecto. Por favor, usa HH:MM.")
                    return str(resp)
  
            descripcion_match = re.search(r'(\d{1,2}:\d{2})', horario_y_descripcion)

            if descripcion_match:
                evento = horario_y_descripcion[descripcion_match.end():].strip()
            else:
                evento = "Evento sin descripción"
  
            if not evento:
                 evento = "Evento sin descripción"
  
            eventos_del_dia = get_events_for_day_and_time(dia, fecha, hora)
            conflicto = len(eventos_del_dia) > 0
  
            if conflicto:
                conflicting_event_id, evento_conflicto, hora_conflicto, conflicting_is_recurring = eventos_del_dia[0]
                fecha_str_new = fecha.strftime('%Y-%m-%d') if fecha else None
                CONVERSATION_STATE[from_number] = {
                    'conflicting_event_id': conflicting_event_id,
                    'new_event_data': {
                        'evento': evento,
                        'dia': dia,
                        'fecha_str': fecha_str_new,
                        'hora': hora,
                        'recurrente': recurrente
                    }
                }
  
                message_conflict = f"¡Atención! Hay un conflicto de horario. Ya tienes el evento '{evento_conflicto}' a las {hora_conflicto}.\n¿Qué quieres hacer?\n"

                if conflicting_is_recurring:
                    message_conflict += "1. Conservar el evento nuevo (solo para esta fecha)\n"
                else:
                    message_conflict += "1. Conservar el evento nuevo (eliminará el antiguo)\n"

                message_conflict += "2. Conservar el evento existente\nResponde con '1' o '2'."

                resp.message(message_conflict)
            else:
                if fecha_fin:
                    current_date = datetime.date.today()
                    day_index = list(DIA_SEMANA_MAP.values()).index(dia)

                    while current_date.weekday() != day_index:
                        current_date += datetime.timedelta(days=1)
  
                    added_count = 0

                    while current_date <= fecha_fin:
                        if insert_event(evento, dia, current_date, hora, False):
                            added_count += 1
                        current_date += datetime.timedelta(days=7)
  
                    resp.message(f"¡Evento '{evento}' agregado para todos los {get_spanish_day_name(dia).lower()} hasta el {fecha_fin.strftime('%d/%m/%Y')}!")
                else:
                    fecha_str = fecha.strftime('%Y-%m-%d') if fecha else None
                    if insert_event(evento, dia, fecha, hora, recurrente):
                        if recurrente:
                            dia_espanol = get_spanish_day_name(dia)
                            resp.message(f"¡Evento '{evento}' agregado para todos los {dia_espanol.lower()} a las {hora}!")
                        else:
                            fecha_espanol_str = fecha.strftime('%d/%m/%Y') if fecha else ""
                            dia_espanol = get_spanish_day_name(dia)
                            resp.message(f"¡Evento '{evento}' agregado para el {dia_espanol} {fecha_espanol_str} a las {hora}!")
                    else:
                        resp.message("Hubo un error al agregar el evento. Por favor, inténtalo de nuevo.")
 
        except (IndexError, ValueError, re.error) as e:
            print(f"Error al procesar el mensaje: {e}")
            resp.message("Hubo un error al procesar el formato del mensaje. Asegúrate de usar un formato claro. Ejemplos: 'agregar evento hoy a las 10:00 reunión', 'agregar evento 26/08/2025 a las 12:00 arreglar la sala', o 'agregar evento todos los martes hasta el 26/08/2025 a las 9:00 clases en la U'")
  
    # --- Lógica para mostrar todos los eventos programados ---
    elif "mostrar eventos" in msg.lower():
        eventos = get_all_events()
 
        if eventos:
            MAX_MESSAGE_LENGTH = 1500
            ahora = datetime.datetime.now()
            eventos_con_proxima_fecha = []
  
            # Mapeo de días de la semana de inglés a español
            # La función get_spanish_day_name ya hace esto, pero es útil tener el mapeo
            # aquí para la lógica de búsqueda de la próxima fecha.
            english_days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
  
            for id, data in eventos:
                if data.get("recurrente"):
                    # Calcular la próxima fecha para un evento recurrente
                    dia_semana_recurrente = data.get("dia_semana")
 
                    # Encontrar el índice del día de la semana actual
                    dia_semana_ahora = ahora.weekday() # Lunes es 0, Domingo es 6
 
                    # Encontrar el índice del día de la semana del evento
                    dia_semana_evento = english_days.index(dia_semana_recurrente)
  
                    # Calcular cuántos días faltan para el próximo evento
                    dias_a_sumar = dia_semana_evento - dia_semana_ahora

                    if dias_a_sumar < 0:
                        dias_a_sumar += 7
  
                    # Si el evento es hoy, revisamos la hora
                    hora_evento_str = data.get("hora")
                    hora_evento = datetime.datetime.strptime(hora_evento_str, '%H:%M').time()
  
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
                    evento_datetime = datetime.datetime.strptime(f"{fecha_evento_str} {hora_evento_str}", '%Y-%m-%d %H:%M')
  
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
                        data["conteo"]
                    )
  
                    # Construimos la línea de texto para el evento actual
                    if recurrente:
                        dia_espanol = get_spanish_day_name(dia_semana)
                        linea_evento = f"Todos los {dia_espanol.lower()} a las {hora}: {evento}\n"
                    else:
                        fecha_obj = datetime.datetime.strptime(fecha, '%Y-%m-%d')
                        dia_espanol = get_spanish_day_name(fecha_obj.strftime('%A'))
                        fecha_formateada = fecha_obj.strftime('%d/%m/%Y')
                        linea_evento = f"{dia_espanol} {fecha_formateada} a las {hora}: {evento}\n"
  
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
        eventos = get_events_for_a_day(dia_texto)
 
        if eventos:
            mensaje = f"Eventos programados para el {dia_texto.capitalize()}:\n"
            # Ahora usamos el conteo para mostrar en el mensaje
            for id, evento, hora, _, _, conteo in eventos:
                mensaje += f"{conteo}: {hora}: {evento}\n"
        else:
            mensaje = f"No tienes eventos programados para el {dia_texto.capitalize()}."
        resp.message(mensaje)
 
    elif "listar eventos" in msg.lower():
        eventos = get_events_for_today()
        eventos_pendientes = []
        hora_actual_obj = datetime.datetime.now().time()
  
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
  
if __name__ == "__main__":
    scheduler = BackgroundScheduler()
    scheduler.add_job(daily_routine_message, 'cron', hour=5, minute=0)
    scheduler.add_job(schedule_reminders, 'cron', hour=4, minute=55)
    scheduler.start()
 
    app.run(debug=True)
