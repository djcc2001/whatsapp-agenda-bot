"""WhatsApp Event Bot - Main Application Module.

This module replaces the original monolithic app.py with a modular structure:
- routes: Flask endpoints (webhook, health checks)
- services: Twilio, Firestore, Gemini integrations
- models: Data structures for events/reminders
- utils: Date handling, timezone, command parsing
"""

import logging
import os
import sys
import time
import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from routes import create_app
from services import TwilioService, FirestoreService
from utils import LOCAL_TIMEZONE, get_timezone, get_spanish_day_name

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


# Scheduler job functions using modular services
def daily_routine_message(twilio_service, firestore_service, your_phone_number):
    """Genera y envía el mensaje de rutina matutina con ejemplos de comandos."""
    eventos = firestore_service.get_events_for_today()
    dia_semana_actual_es = get_spanish_day_name(datetime.date.today().strftime('%A'))

    if eventos:
        mensaje = f"¡Buenos días! Tu rutina para hoy ({dia_semana_actual_es}) es:\n"

        for id, evento, hora, conteo in eventos:
            mensaje += f"• {conteo}: {hora}: {evento}\n"

    else:
        mensaje = f"¡Buenos días! No tienes eventos programados para hoy ({dia_semana_actual_es})."

    twilio_service.send_message(your_phone_number, mensaje)


def schedule_reminders(twilio_service, firestore_service, your_phone_number):
    """Programa los recordatorios para los eventos del día."""
    eventos = firestore_service.get_events_for_today()
    ahora = datetime.datetime.now(get_timezone())

    for id, evento, hora_db, conteo in eventos:
        try:
            hora_evento_obj = datetime.datetime.strptime(hora_db, '%H:%M')
        except ValueError:
            continue

        hora_recordatorio = hora_evento_obj - datetime.timedelta(minutes=15)
        fecha_recordatorio = datetime.datetime.combine(ahora.date(), hora_recordatorio.time())

        if fecha_recordatorio > ahora:
            twilio_service.send_message(
                your_phone_number,
                f"Recordatorio: Tienes '{evento}' en 15 minutos."
            )


def main():
    """Entry point for the application."""
    from routes import create_app

    app = create_app()

    # Get host and port from environment (default to development values)
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "5000"))

    # Initialize Twilio and Firestore services for scheduler jobs
    twilio_service = TwilioService(
        account_sid=os.environ.get("TWILIO_ACCOUNT_SID", ""),
        auth_token=os.environ.get("TWILIO_AUTH_TOKEN", ""),
        whatsapp_number=os.environ.get("TWILIO_WHATSAPP_NUMBER", ""),
    )
    firestore_service = FirestoreService(db=None)  # db may be None if not configured

    logger.info("Iniciando WhatsApp Event Bot...")
    logger.info("Servidor disponible en http://%s:%s", host, port)

    # Initialize and start scheduler
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        daily_routine_message,
        'cron',
        hour=14,
        minute=10,
        timezone='America/Lima',
        args=[twilio_service, firestore_service, os.environ.get("YOUR_PHONE_NUMBER", "")],
    )
    scheduler.add_job(
        schedule_reminders,
        'cron',
        hour=4,
        minute=55,
        timezone='America/Lima',
        args=[twilio_service, firestore_service, os.environ.get("YOUR_PHONE_NUMBER", "")],
    )
    scheduler.start()
    logger.info("Scheduler iniciado correctamente.")

    logger.info("Servidor disponible en http://%s:%s", host, port)

    # Mantiene el proceso vivo para que el scheduler pueda ejecutarse
    try:
        while True:
            time.sleep(2)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler detenido.")
        scheduler.shutdown()


if __name__ == "__main__":
    main()