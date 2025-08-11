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

2. **Crear y activar entorno virtual**
  ```bash
  python -m venv venv
  # Windows
  venv\Scripts\activate
  # Linux/Mac
  source venv/bin/activate

3. **Crear y activar entorno virtual**
  









