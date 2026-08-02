from sqlalchemy.orm import declarative_base

Base = declarative_base()

from app.models.user import User
from app.models.vehicle import Vehicle
from app.models.passenger import Passenger
from app.models.ride_request import RideRequest
from app.models.ride_offer import RideOffer