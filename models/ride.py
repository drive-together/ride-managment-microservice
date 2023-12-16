from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Ride(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    departure = db.Column(db.DateTime, nullable=False)
    arrival = db.Column(db.DateTime, nullable=False)
    origin = db.Column(db.String(80), nullable=False)
    destination = db.Column(db.String(80), nullable=False)

    user_id = db.Column(db.Integer, nullable=False)

    def to_dict(self):
        return {'id': self.id, 'departure': self.departure, 'arrival': self.arrival, 'origin': self.origin, 'destination': self.destination, 'user_id': self.user_id}