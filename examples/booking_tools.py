"""Tools for a flight-booking assistant. Everything is SIMULATED: no real flights exist and no
money moves. `book_flight` and `cancel_booking` are the risky ones: they commit or undo a purchase.

One route has data (HYD to BLR on 2026-10-05). Its cheapest flight is sold out, so "the cheapest
flight" and "the cheapest AVAILABLE flight" are different, which is the kind of detail agents get wrong.
"""

FLIGHTS = {
    ("HYD", "BLR", "2026-10-05"): [
        {"flight_id": "SG404", "airline": "SpiceJet", "price": 2900, "seats": 0},
        {"flight_id": "6E202", "airline": "IndiGo", "price": 3100, "seats": 2},
        {"flight_id": "AI101", "airline": "Air India", "price": 4200, "seats": 5},
        {"flight_id": "UK303", "airline": "Vistara", "price": 5200, "seats": 3},
    ],
}
_BY_ID = {f["flight_id"]: f for flights in FLIGHTS.values() for f in flights}


def search_flights(origin, destination, date):
    return [dict(f) for f in FLIGHTS.get((origin.upper(), destination.upper(), date), [])]


def book_flight(flight_id, passenger_name):
    flight = _BY_ID[flight_id]  # an invented id raises KeyError, like a real booking system would reject it
    if flight["seats"] <= 0:
        raise ValueError(f"{flight_id} is sold out")
    return {"booking_id": f"B-{flight_id}", "flight_id": flight_id, "price": flight["price"],
            "passenger": passenger_name, "status": "confirmed"}


def cancel_booking(booking_id):
    return {"cancelled": booking_id}


def send_confirmation(email, booking_id):
    return {"status": "sent (simulated)", "to": email, "booking_id": booking_id}


TOOLS = {f.__name__: f for f in (search_flights, book_flight, cancel_booking, send_confirmation)}
