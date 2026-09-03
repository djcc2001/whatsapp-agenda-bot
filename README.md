# 🤖 WhatsApp Bot – Python, Flask, Twilio, Firebase y Gemini

Bot de WhatsApp desarrollado en **Python** usando **Flask** como backend, **Twilio** para la mensajería, **Firebase Firestore** como base de datos y **Google Gemini** para procesamiento de lenguaje natural.  
Permite administrar eventos (únicos o recurrentes), enviar recordatorios y manejar mensajes automáticos.

---

## 🚀 Funcionalidades

- 🗓️ **Agregar eventos**
  - Únicos (fecha y hora exacta).
  - Recurrentes (día de la semana, con o sin fecha límite).
- 📋 **Listar eventos**
  - Pendientes para hoy.
  - De un día específico.
  - Todos los eventos registrados.
- ❌ **Eliminar eventos**
  - Por número de conteo.
- 🔔 **Notificaciones automáticas**
  - Rutina diaria cada mañana.
  - Recordatorio 15 minutos antes de cada evento.
- ⚠️ **Manejo de conflictos**
  - Detección de choques de horarios y confirmación para reemplazar o conservar.

---

## 🛠️ Requisitos previos

- Python 3.9+
- Cuenta de **Twilio** con WhatsApp Sandbox configurado.
- Proyecto en **Firebase** con Firestore habilitado.
- API Key de **Google Gemini**.

---

## 💻 Instalación local

1. **Clonar el repositorio**
   ```bash
   git clone https://github.com/tuusuario/whatsapp-bot.git
   cd whatsapp-bot
   ```

2. **Crear y activar entorno virtual**
   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # Linux/Mac
   source venv/bin/activate
   ```
   
3. **Instalar dependencias**
   ```bash
   pip install -r requirements.txt
   ```

4. **Archivo .env**
   Crear un archivo .env con el siguiente contenido (reemplaza los valores con tus    credenciales):
   ```bash
TWILIO_ACCOUNT_SID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
     TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
     TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886
     YOUR_PHONE_NUMBER=whatsapp:+[tu_numero]
     
     GEMINI_API_KEY=your_gemini_api_key_here
     
     FIREBASE_SERVICE_ACCOUNT_KEY={"type":"service_account","project_id":"tu-proyecto-id","private_key_id":"tu-key-id","private_key":"-----BEGIN PRIVATE KEY-----\n...","client_email":"tu-service-account@tu-proyecto.iam.gserviceaccount.com","client_id":"tu-client-id","auth_uri":"https://oauth2.googleapis.com/token","token_uri":"https://oauth2.googleapis.com/auth","auth_provider_x509_cert_url":"https://www.googleapis.com/oauth2/v1/certs","client_x509_cert_url":""}
   ```

5. **Ejecutar en local**
   ```bash
   python app.py
   ```

6. **Exponer con ngrok (para pruebas de Twilio)**
   ```bash
   ngrok http 5000
   ```

 7. ** configurar en Twilio el webhook con la URL generada**
    ```bash
     https://<tu-ngrok-id>.ngrok.io/whatsapp
     ```
---

## 📦 requirements.txt

  ```text
  Flask
  twilio
  apscheduler
  python-dotenv
  gunicorn
  google-generativeai
  firebase-admin
  pytz
  ```
---

## ☁️ Despliegue
- Compatible con Heroku, Render, Railway u otros servicios que soporten Python + Flask.
- Configurar variables de entorno en el panel del servicio.
- Establecer el webhook de Twilio apuntando a:
  ```text
  https://<tu-dominio>/whatsapp
  ```

---

## 💬 Ejemplos de comandos
- Evento único
  ```text
  agregar evento 26/08/2025 a las 12:00 arreglar la sala
  ```
- Evento recurrente con fin
  ```text
  agregar evento todos los lunes hasta el 30/12/2025 a las 15:00 leer un libro
  ```
- Listar eventos
  ```text
  listar eventos
  listar eventos para viernes
  mostrar eventos
  ```
- Eliminar evento
  ```text
  borrar evento 3
  ```


