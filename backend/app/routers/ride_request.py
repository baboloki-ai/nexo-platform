from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.services.shared_ride_service import SharedRideService
from app.database.dependencies import get_db
from app.models.ride_request import RideRequest
from app.models.user import User
from app.schemas.ride_request import (
    CounterOfferOptionsResponse,
    DriverRespondRequest,
    DriverResponseOut,
    FareQuoteRequest,
    FareQuoteResponse,
    NegotiationEventOut,
    PassengerOfferUpdate,
    RideRequestCreate,
    RideRequestResponse,
    SelectDriverRequest,
    SharedRideConsentRequest,
)
from app.services.driver_identity_service import DriverIdentityService
from app.services.driver_service import DriverService
from app.services.marketplace_service import MarketplaceService
from app.services.next_ride_service import NextRideService
from app.services.pricing_service import PricingService
from app.services.ride_service import RideService
from app.utils.dependencies import get_current_user

router = APIRouter(
    prefix="/rides",
    tags=["Ride Requests"]
)


@router.post("/quote", response_model=FareQuoteResponse)
def quote_fare(
    payload: FareQuoteRequest,
    _current_user: User = Depends(get_current_user),
):
    quote = PricingService.quote_trip(
        payload.pickup_latitude,
        payload.pickup_longitude,
        payload.destination_latitude,
        payload.destination_longitude,
    )
    return PricingService.serialize_quote(quote)


@router.post("/", response_model=RideRequestResponse)
def create_ride_request(
    ride: RideRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return DriverIdentityService.serialize_ride(
        db,
        RideService.create_ride(
            db=db,
            current_user=current_user,
            pickup_location=ride.pickup_location,
            pickup_latitude=ride.pickup_latitude,
            pickup_longitude=ride.pickup_longitude,
            destination=ride.destination,
            destination_latitude=ride.destination_latitude,
            destination_longitude=ride.destination_longitude,
            proposed_fare=ride.proposed_fare
        ),
    )


@router.get("/available", response_model=list[RideRequestResponse])
def get_available_rides(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != "driver":
        raise HTTPException(
            status_code=403,
            detail="Only drivers can view available rides.",
        )
    return DriverIdentityService.serialize_rides(
        db,
        RideService.get_available_rides(db),
    )
@router.get(
    "/{ride_id}/shared-candidates",
    response_model=list[RideRequestResponse],
)
def get_shared_ride_candidates(
    ride_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_ride = db.query(RideRequest).filter(
        RideRequest.id == ride_id
    ).first()

    if current_ride is None:
        raise HTTPException(status_code=404, detail="Ride not found.")

    candidates = SharedRideService.find_candidates(
        db=db,
        current_ride=current_ride,
        driver=current_user,
    )

    return DriverIdentityService.serialize_rides(db, candidates)


@router.post(
    "/{ride_id}/shared-candidates/{candidate_id}/propose",
    response_model=RideRequestResponse,
)
def propose_shared_ride(
    ride_id: int,
    candidate_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return DriverIdentityService.serialize_ride(
        db,
        SharedRideService.propose(
            db=db,
            ride_id=ride_id,
            candidate_id=candidate_id,
            current_user=current_user,
        ),
    )


@router.post("/{ride_id}/shared-consent", response_model=RideRequestResponse)
def consent_to_shared_ride(
    ride_id: int,
    payload: SharedRideConsentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return DriverIdentityService.serialize_ride(
        db,
        SharedRideService.record_consent(
            db=db,
            ride_id=ride_id,
            current_user=current_user,
            consent=payload.consent,
        ),
    )


@router.get("/my", response_model=list[RideRequestResponse])
def get_my_rides(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return DriverIdentityService.serialize_rides(
        db,
        RideService.get_passenger_rides(
            db=db,
            current_user=current_user
        ),
    )


@router.put("/{ride_id}/accept-next", response_model=RideRequestResponse)
def accept_next_ride(
    ride_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return DriverIdentityService.serialize_ride(
        db,
        NextRideService.accept_next_ride(
            db=db,
            ride_id=ride_id,
            current_user=current_user,
        ),
    )


@router.put("/{ride_id}/accept", response_model=RideRequestResponse)
def accept_ride(
    ride_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return DriverIdentityService.serialize_ride(
        db,
        RideService.accept_ride(
            db=db,
            ride_id=ride_id,
            current_user=current_user
        ),
    )


@router.put("/{ride_id}/reject")
def reject_ride(
    ride_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    ride = DriverService.reject_ride(
        db=db,
        ride_id=ride_id,
        driver_id=current_user.id
    )

    if ride is None:
        raise HTTPException(
            status_code=404,
            detail="Ride not found or cannot be rejected."
        )

    return {
        "message": "Ride rejected successfully.",
        "ride": ride
    }


@router.put("/{ride_id}/offer", response_model=RideRequestResponse)
def update_passenger_offer(
    ride_id: int,
    payload: PassengerOfferUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return DriverIdentityService.serialize_ride(
        db,
        MarketplaceService.update_passenger_offer(
            db=db,
            ride_id=ride_id,
            current_user=current_user,
            action=payload.action,
            amount=payload.amount,
            passenger_offer_version=payload.passenger_offer_version,
        ),
    )


@router.get(
    "/{ride_id}/counter-options",
    response_model=CounterOfferOptionsResponse,
)
def get_counter_options(
    ride_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return MarketplaceService.get_counter_options(
        db=db,
        ride_id=ride_id,
        current_user=current_user,
    )


@router.put("/{ride_id}/respond", response_model=RideRequestResponse)
def respond_to_ride(
    ride_id: int,
    payload: DriverRespondRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return DriverIdentityService.serialize_ride(
        db,
        MarketplaceService.driver_respond(
            db=db,
            ride_id=ride_id,
            current_user=current_user,
            response_type=payload.response_type,
            amount=payload.amount,
        ),
    )


@router.get("/{ride_id}/responses", response_model=list[DriverResponseOut])
def list_driver_responses(
    ride_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return MarketplaceService.list_responses(
        db=db,
        ride_id=ride_id,
        current_user=current_user,
    )


@router.get("/{ride_id}/negotiation", response_model=list[NegotiationEventOut])
def list_negotiation_history(
    ride_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return MarketplaceService.list_negotiation(
        db=db,
        ride_id=ride_id,
        current_user=current_user,
    )


@router.put("/{ride_id}/select", response_model=RideRequestResponse)
def select_driver(
    ride_id: int,
    payload: SelectDriverRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return DriverIdentityService.serialize_ride(
        db,
        MarketplaceService.select_driver(
            db=db,
            ride_id=ride_id,
            current_user=current_user,
            response_id=payload.response_id,
        ),
    )


@router.put(
    "/{ride_id}/responses/{response_id}/ignore",
    response_model=RideRequestResponse,
)
def ignore_driver_response(
    ride_id: int,
    response_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return DriverIdentityService.serialize_ride(
        db,
        MarketplaceService.ignore_response(
            db=db,
            ride_id=ride_id,
            response_id=response_id,
            current_user=current_user,
        ),
    )


@router.put("/{ride_id}/arrive", response_model=RideRequestResponse)
def arrive_at_pickup(
    ride_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return DriverIdentityService.serialize_ride(
        db,
        RideService.arrive_at_pickup(
            db=db,
            ride_id=ride_id,
            current_user=current_user
        ),
    )


@router.put(
    "/{ride_id}/driver-arrived",
    response_model=RideRequestResponse
)
def driver_arrived(
    ride_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return DriverIdentityService.serialize_ride(
        db,
        RideService.driver_arrived(
            db=db,
            ride_id=ride_id,
            current_user=current_user
        ),
    )


@router.put("/{ride_id}/start", response_model=RideRequestResponse)
def start_ride(
    ride_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return DriverIdentityService.serialize_ride(
        db,
        RideService.start_ride(
            db=db,
            ride_id=ride_id,
            current_user=current_user
        ),
    )


@router.put("/{ride_id}/complete", response_model=RideRequestResponse)
def complete_ride(
    ride_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return DriverIdentityService.serialize_ride(
        db,
        RideService.complete_ride(
            db=db,
            ride_id=ride_id,
            current_user=current_user
        ),
    )


@router.put("/{ride_id}/cancel", response_model=RideRequestResponse)
def cancel_ride(
    ride_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return DriverIdentityService.serialize_ride(
        db,
        RideService.cancel_ride(
            db=db,
            ride_id=ride_id,
            current_user=current_user
        ),
    )