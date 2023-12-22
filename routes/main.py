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
    'service': 'ride-management-microservice',
}

create_rides_counter = metrics.counter(
    'create_rides_counter',
    'Number of create rides calls',
    labels={'endpoint': '/api/rides'}
)
get_rides_counter = metrics.counter(
    'get_rides_counter',
    'Number of get rides calls',
    labels={'endpoint': '/api/rides'}
)

gmaps = googlemaps.Client(key=GOOGLE_DIRECTIONS_API_KEY)

@timeout(5)
def get_user(user_id):
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
    graphql_payload = {
        'query': graphql_query,
        'variables': {
            'userId': user_id
        }
    }

    response = requests.post(f'http://{ACCOUNT_MANAGMENT_SERVICE_HOST}:{ACCOUNT_MANAGMENT_SERVICE_PORT}/api/users', headers=headers, json=graphql_payload)
    if response.status_code == 200:
        user = response.json()
        logger.info(f'User retrieved: {user}', extra=extra)
        return user
    
    logger.error(f'Error retrieving user: {response.json()}', extra=extra)
    return None

@main_bp.route('/rides', methods=['GET'])
def rides_page():
    """
    Retrieves a list of rides along with user information.

    ---
    responses:
      200:
        description: Returns a list of rides and associated user details.
    """

    res=[]
    rides = Ride.query.all()
    for ride in rides:
        user_id = ride.user_id
        try:
            user = get_user(user_id)
        except Exception as e:
            user = None
        entry = {
            'ride': ride.to_dict(),
            'user': user
        }
        res.append(entry)
        
    logger.info("Rendedred rides", extra=extra)
    return render_template('rides.html', rides=res)

@main_bp.route('/create', methods=['GET'])
def create_rides_page():
    """
    Renders the page for creating new rides.

    ---
    responses:
      200:
        description: Returns the HTML page for creating rides.
    """
    logger.info("Create rides page rendered", extra=extra)
    return render_template('create.html')


@main_bp.route('/api/rides', methods=['POST'])
@create_rides_counter
@jwt_required()
def create_rides():
    """
    Creates a new ride based on the provided information.

    ---
    parameters:
      - name: Authorization
        in: header
        type: string
        required: true
        default: Bearer <JWT_TOKEN>
        description: The JWT token in the format 'Bearer <JWT_TOKEN>'.
      - name: Ride
        in: body
        type: object
        required: true
        schema:
            id: Ride
            properties:
                departure:
                    type: string
                    format: date-time
                    description: The departure time of the ride.
                origin:
                    type: string
                    description: The origin of the ride.
                destination:
                    type: string
                    description: The destination of the ride.
    responses:
      200:
        description: Returns the details of the newly created ride.
    """
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

    logger.info(f'New ride created: {new_ride.to_dict()}', extra=extra)
    return jsonify(new_ride.to_dict()), 200

@main_bp.route('/api/rides', methods=['GET'])
@get_rides_counter
def get_rides():
    """
    Retrieves a list of rides along with associated user details.

    ---
    responses:
      200:
        description: Returns a JSON array of rides and user information.
    """

    res=[]
    rides = Ride.query.all()
    for ride in rides:
        user_id = ride.user_id
        try:
            user = get_user(user_id)
        except Exception as e:
            user = None
        
        entry = {
            'ride': ride.to_dict(),
            'user': user
        }
        res.append(entry)
        
    logger.info("Rides retrieved", extra=extra)
    return jsonify(res), 200


@timeout(5) #TODO test on linux
def timeout(seconds):
    import time
    time.sleep(seconds)

@main_bp.route('/api/timeout_test/<int:seconds>', methods=['GET'])
async def timeout_test(seconds):
    """
    Tests the timeout functionality.

    ---
    parameters:
      - name: seconds
        in: path
        type: integer
        required: true
        description: The duration in seconds for the timeout.
    responses:
      200:
        description: Returns "OK" if the timeout test is successful.
    """
    try:
        timeout(seconds)
        return jsonify("OK"), 200
    except Exception as e:
        print(e)
        return jsonify(None), 200 #Fallback
    

@circuit(failure_threshold=2, expected_exception=TimeoutError)
@main_bp.route('/api/circuit_breaker_test', methods=['GET'])
def circuit_breaker_test():
    """
    Tests the circuit breaker functionality.

    ---
    responses:
      200:
        description: Returns "OK" if the timeout test is successful.
    """
    timeout(6)
    return jsonify("OK"), 200