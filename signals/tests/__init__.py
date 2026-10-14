"""Tests for the bar-anchored signal engine.

This is a package (``__init__.py`` present) so pytest imports its modules as
``signals.tests.test_*`` rather than as bare top-level names. Without it, this
directory's ``test_indicators.py`` collides with ``tests/test_indicators.py`` and
the whole suite fails collection with an "import file mismatch" error.

Kept out of the shipped distribution: ``tests`` is in the packaging guard's
excluded set, and ``pyproject.toml``'s explicit package list contains ``signals``
but not ``signals.tests``.
"""
