"""Prepared notification views for trip-specific mail delivery."""

from .trip_mail_view import TripMailView, prepare_trip_mail_view

__all__ = ["TripMailView", "prepare_trip_mail_view"]
