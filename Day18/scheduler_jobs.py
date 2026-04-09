from aggregation_service import aggregate_recent_readings
from collector_temperature import collect_latest_temperature_readings
from summary_service import generate_periodic_summary


def collect_readings_job() -> dict:
    return collect_latest_temperature_readings()


def aggregate_readings_job() -> dict:
    return aggregate_recent_readings(window_type="15m", interval_minutes=15)


def generate_summary_job() -> dict:
    return generate_periodic_summary(summary_type="hourly")
