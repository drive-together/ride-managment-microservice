from flask import Flask, render_template, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from prometheus_flask_exporter import PrometheusMetrics
from sqlalchemy import text
import logging
import logstash
from timeout_decorator import timeout
from circuitbreaker import circuit, CircuitBreakerError
from flasgger import Swagger
import time
from routes.main import main_bp
from models.ride import db
from settings import LOGIT_IO_HOST, LOGIT_IO_PORT

global alive
alive = True

def create_app():
    app = Flask(__name__)
    app.config.from_pyfile('settings.py')   
    
    CORS(app)

    db.init_app(app)
    with app.app_context():
        db.create_all()

    jwt = JWTManager(app)

    metrics = PrometheusMetrics(app)

    swagger_config = {
        "headers": [],
        "specs": [
            {
                "endpoint": 'apispec',
                "route": '/ride-managment/apispec.json',
                "rule_filter": lambda rule: True,  # all in
                "model_filter": lambda tag: True,  # all in
            }
        ],
        "static_url_path": "/flasgger_static",
        "swagger_ui": True,
        "specs_route": "/opendoc"
    }
    template = {
        "swagger": "2.0",
        "basePath": "/ride-managment",
    }
    swagger = Swagger(app, config=swagger_config, template=template)

    logger = logging.getLogger('python-logstash-logger')
    logger.setLevel(logging.INFO)
    logger.addHandler(logstash.UDPLogstashHandler(
        host=LOGIT_IO_HOST, 
        port=LOGIT_IO_PORT,
        version=1
    ))
    app.logger.addHandler(logger)

    app.register_blueprint(main_bp)

    @app.route('/', methods=['GET'])
    def index():
        return jsonify(), 200
    
    @app.route('/livez', methods=['GET'])
    def health_check_liveness():
        global alive
        if not alive:
            return jsonify(status='error', message='Health check failed'), 500
        
        return jsonify(status='ok', message='Health check passed'), 200
        
    @app.route('/readyz', methods=['GET'])
    def health_check_readiness():
        try:
            db.session.execute(text('SELECT 1'))
            return jsonify(status='ok', message='Health check passed'), 200
        except Exception as e:
            return jsonify(status='error', message=f'Health check failed: {str(e)}'), 500
    

    # Test endpoints
    @app.route('/liveness_test', methods=['GET'])
    def liveness_test():
        global alive
        alive = False

        return jsonify("Ready set to false"), 200
    
    @timeout(3, use_signals=False)
    def test_timeout(seconds):
        time.sleep(seconds)
        return jsonify("OK"), 200

    @circuit(failure_threshold=2, recovery_timeout=7)
    def test_circuit(seconds):
        return test_timeout(seconds)

    @app.route('/timeout_test/<int:seconds>', methods=['GET'])
    async def timeout_test(seconds):
        try:
            return test_timeout(seconds)
        except Exception as e:
            return jsonify("Timeout fallback"), 200 #Fallback

    @app.route('/circuit_breaker_test/<int:seconds>', methods=['GET'])
    def circuit_breaker_test(seconds):
        try:
            return test_circuit(seconds)
        except CircuitBreakerError as e:
            return jsonify("Circuit breaker fallback"), 200

    return app