import pytest

from agentprobe import Probe, TrajectoryAssertionError


def run(search_result=None, book_id="F1", search_fails=False, skip_search=False):
    probe = Probe()

    def search_flights():
        if search_fails:
            raise TimeoutError("timed out")
        return search_result

    def book_flight(flight_id):
        return {"booking_id": f"B-{flight_id}"}

    if not skip_search:
        try:
            probe.wrap(search_flights)()
        except TimeoutError:
            pass
    probe.wrap(book_flight)(flight_id=book_id)
    return probe.trajectory


FLIGHTS = [{"flight_id": "F1", "price": 100}, {"flight_id": "F2", "price": 200}]


def check(trajectory):
    return trajectory.arg_from_result("book_flight", "flight_id", "search_flights", "flight_id")


def test_a_flight_id_from_the_search_passes():
    assert check(run(FLIGHTS, book_id="F2")) is not None


def test_an_invented_flight_id_is_caught_and_the_real_ones_are_listed():
    with pytest.raises(TrajectoryAssertionError, match=r"(?s)'F9'.*no earlier 'search_flights' result.*\['F1', 'F2'\]"):
        check(run(FLIGHTS, book_id="F9"))


def test_booking_without_any_search_is_caught():
    with pytest.raises(TrajectoryAssertionError, match="without a successful 'search_flights'"):
        check(run(skip_search=True))


def test_a_failed_search_is_not_a_source():
    with pytest.raises(TrajectoryAssertionError, match="without a successful"):
        check(run(search_fails=True))


def test_numbers_and_strings_compare_equal():
    probe = Probe()

    def search():
        return [{"id": 7}]

    def get(item_id):
        return item_id

    probe.wrap(search)()
    probe.wrap(get)(item_id="7")

    probe.trajectory.arg_from_result("get", "item_id", "search", "id")


def test_without_a_field_any_value_in_the_result_counts():
    probe = Probe()

    def search():
        return {"order": {"id": "A1"}}

    def refund(order_id):
        return order_id

    probe.wrap(search)()
    probe.wrap(refund)(order_id="A1")

    probe.trajectory.arg_from_result("refund", "order_id", "search")


def test_a_text_result_provides_its_words():
    probe = Probe()

    def search():
        return "Found flight F1 for 100"

    def book(flight_id):
        return flight_id

    probe.wrap(search)()
    probe.wrap(book)(flight_id="F1")

    probe.trajectory.arg_from_result("book", "flight_id", "search")


def test_calls_that_do_not_use_the_argument_are_ignored():
    trajectory = Probe().trajectory  # nothing recorded

    assert trajectory.arg_from_result("book_flight", "flight_id", "search_flights") is trajectory
