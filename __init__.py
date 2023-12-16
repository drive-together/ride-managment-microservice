from flask import Flask, render_template, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from prometheus_flask_exporter import PrometheusMetrics
from sqlalchemy import text
import logging
import logstash
from flasgger import Swagger
from routes.main import main_bp
from models.ride import db
from settings import LOGIT_IO_HOST, LOGIT_IO_PORT

def create_app():
    app = Flask(__name__)
    app.config.from_pyfile('settings.py')
    
    CORS(app)

    # Initialize extensions
    db.init_app(app)
    jwt = JWTManager(app)
    metrics = PrometheusMetrics(app)
    swagger = Swagger(app)

    # Register blueprints
    app.register_blueprint(main_bp)

    # Create the database tables
    with app.app_context():
        db.create_all()

    @app.route('/index')
    def index():
        return render_template('index.html')
    
    
    @app.route('/livez', methods=['GET'])
    def health_check_liveness():
        return jsonify(status='ok', message='Health check passed'), 200
        
    @app.route('/readyz', methods=['GET'])
    def health_check_readiness():
        try:
            db.session.execute(text('SELECT 1'))
            return jsonify(status='ok', message='Health check passed'), 200
        except Exception as e:
            return jsonify(status='error', message=f'Health check failed: {str(e)}'), 500       

    logger = logging.getLogger('python-logstash-logger')
    logger.setLevel(logging.INFO)
    logger.addHandler(logstash.UDPLogstashHandler(
        host=LOGIT_IO_HOST, 
        port=LOGIT_IO_PORT,
        version=1
    ))

    app.logger.addHandler(logger)

    return app