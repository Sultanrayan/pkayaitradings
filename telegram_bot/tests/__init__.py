"""Tests for the Telegram signal bot.

This is a package, not a loose directory, and the reason is a filename collision
rather than taste. ``telegram_bot/tests/test_indicators.py`` and the repository's
own ``tests/test_indicators.py`` have the same module name; without ``__init__.py``
pytest's rootdir-based import puts both on ``sys.path`` as top-level
``test_indicators`` and one of them silently shadows the other. With this marker
the module is ``telegram_bot.tests.test_indicators`` and cannot collide.
"""
