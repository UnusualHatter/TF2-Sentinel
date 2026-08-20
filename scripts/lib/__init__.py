"""Shared library code for the TF2 Sentinel data pipeline.

Everything under ``scripts/`` operates on the flat-file database in
``data/normalized/*.csv``. There is no ORM and no external dependency
beyond the Python standard library — the pipeline only ever has to run
occasionally, by hand, so keeping it dependency-free matters more than
convenience.
"""
