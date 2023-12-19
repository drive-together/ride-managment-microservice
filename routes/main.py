from flask import Blueprint, jsonify, request, render_template
from flask_jwt_extended import jwt_required, get_jwt_identity
from prometheus_flask_exporter import PrometheusMetrics
import logging
from timeout_decorator import timeout
from circuitbreaker import circuit, CircuitBreakerError
from models.ride import db, Ride
import requests
import googlemaps
from datetime import datetime, timedelta
from settings import GOOGLE_DIRECTIONS_API_KEY, ACCOUNT_MANAGMENT_SERVICE_HOST, ACCOUNT_MANAGMENT_SERVICE_PORT

main_bp = Blueprint('main', __name__)
metrics = PrometheusMetrics(main_bp)
logger = logging.getLogger('python-logstash-logger')
extra = {
    'service': 'ride_sharing',
}

create_rides_counter = metrics.counter(
    'create_rides_counter',
    'Number of successful rides created',
    labels={'endpoint': '/api/rides'}
)

gmaps = googlemaps.Client(key=GOOGLE_DIRECTIONS_API_KEY)

@main_bp.route('/rides', methods=['GET'])
def rides_page():
    headers = {
        'Content-Type': 'application/json',
    }
    graphql_query = '''
        query User($userId: ID!){
            user(id: $userId) {
                id
                username
            }
        }
    '''

    res=[]
    rides = Ride.query.all()
    for ride in rides:
        user_id = ride.user_id

        graphql_payload = {
            'query': graphql_query,
            'variables': {
                'userId': user_id
            }
        }
        response = requests.post(f'http://{ACCOUNT_MANAGMENT_SERVICE_HOST}:{ACCOUNT_MANAGMENT_SERVICE_PORT}/api/users', headers=headers, json=graphql_payload)
        if response.status_code == 200:
            user = response.json()

            entry = {
                'ride': ride.to_dict(),
                'user': user
            }
            res.append(entry)
        

    return render_template('rides.html', rides=res)

@main_bp.route('/create', methods=['GET'])
def create_rides_page():
    """
    Endpoint to perform some operation.

    ---
    responses:
      200:
        description: Successful operation
      500:
        description: An error occurred
    """
    return render_template('create.html')


@main_bp.route('/api/rides', methods=['POST'])
@create_rides_counter
@jwt_required()
def create_rides():
    user_id = get_jwt_identity()

    data = request.get_json()
    departure = datetime.strptime(data.get('departure'), '%Y-%m-%dT%H:%M')
    origin = data.get('origin')
    destination = data.get('destination')

    directions = gmaps.directions(origin, destination, mode='driving')
    duration = directions[0]['legs'][0]['duration']['value']

    arrival = departure + timedelta(seconds=duration)

    new_ride = Ride(departure=departure, arrival=arrival, origin=origin, destination=destination, user_id=user_id)

    db.session.add(new_ride)
    db.session.commit()

    return jsonify(new_ride.to_dict()), 200

@main_bp.route('/api/rides', methods=['GET'])
def get_rides():
    headers = {
        'Content-Type': 'application/json',
    }
    graphql_query = '''
        query User($userId: ID!){
            user(id: $userId) {
                id
                username
            }
        }
    '''

    res=[]
    rides = Ride.query.all()
    for ride in rides:
        user_id = ride.user_id

        graphql_payload = {
            'query': graphql_query,
            'variables': {
                'userId': user_id
            }
        }
        response = requests.post('http://localhost:80/api/users', headers=headers, json=graphql_payload)
        if response.status_code == 200:
            user = response.json()

            entry = {
                'ride': ride.to_dict(),
                'user': user
            }
            res.append(entry)
        
    return jsonify(res), 200


@timeout(5) #TODO test on linux
def timeout(seconds):
    import time
    time.sleep(seconds)

@main_bp.route('/api/timeout_test/<int:seconds>', methods=['GET'])
async def timeout_test(seconds):
    try:
        timeout(seconds)
        return jsonify("OK"), 200
    except Exception as e:
        return jsonify(None), 200 #Fallback
    

@circuit(failure_threshold=2, expected_exception=TimeoutError)
@main_bp.route('/api/circuit_breaker_test', methods=['GET'])
def circuit_breaker_test():
    timeout(6)