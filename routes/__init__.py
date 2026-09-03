"""Flask routes and webhook handlers for the WhatsApp Event Bot."""

import logging

from flask import Flask

from .whatsapp_routes import whatsapp_blueprint

logger = logging.getLogger(__name__)


def create_app() -> Flask:
    """Application factory that creates and configures the Flask app."""
    app = Flask(__name__)

    # Register blueprints
    app.register_blueprint(whatsapp_blueprint)

    # Health check route
    @app.route("/health", methods=["GET"])
    def health():
        """Health check endpoint."""
        return {"status": "ok", "message": "Bot operativo"}, 200

    # Root route for basic info
    @app.route("/", methods=["GET"])
    def index():
        """Basic endpoint with bot info."""
        return {
            "mensaje": "WhatsApp Event Bot API",
            "estado": "activo",
        }, 200

    return app