from flask import Flask
from .extensions import db, migrate, jwt
from .config import config_by_name
import os


def create_app(config_name=None):
    app = Flask(__name__)

    config_name = config_name or os.getenv("FLASK_ENV", "development")
    app.config.from_object(config_by_name[config_name])

    # Init extensions
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)

    # Register pgvector type with SQLAlchemy — MUST happen after db.init_app
    with app.app_context():
        from pgvector.sqlalchemy import Vector  # noqa — registers the type

    # Preload DeepFace model weights at startup (avoids 60s hang on first request)
    # Downloads ArcFace weights ~500MB on very first run, then cached locally
    # Skip during CLI commands (flask db init/migrate/upgrade) to avoid TF/CUDA segfaults
    if not os.getenv("SKIP_DEEPFACE_PRELOAD"):
        with app.app_context():
            import threading
            def _preload():
                try:
                    from deepface import DeepFace
                    import numpy as np
                    dummy = np.zeros((112, 112, 3), dtype=np.uint8)
                    DeepFace.represent(dummy, model_name=app.config["FACE_MODEL"],
                                       enforce_detection=False)
                    app.logger.info("DeepFace model preloaded successfully.")
                except Exception as e:
                    app.logger.warning(f"DeepFace preload failed (non-fatal): {e}")
            threading.Thread(target=_preload, daemon=True).start()

    # Register blueprints
    from .routes.admin import admin_bp
    from .routes.auth import auth_bp
    from .routes.images import images_bp

    app.register_blueprint(admin_bp, url_prefix="/api/v1/admin")
    app.register_blueprint(auth_bp,  url_prefix="/api/v1/auth")
    app.register_blueprint(images_bp, url_prefix="/api/v1/images")

    # Swagger docs (free, built-in via flasgger)
    from flasgger import Swagger
    Swagger(app, template={
        "info": {"title": "Grabpic API", "version": "1.0"},
        "securityDefinitions": {
            "Bearer": {"type": "apiKey", "name": "Authorization", "in": "header"}
        }
    })

    return app
