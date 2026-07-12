"""Protect frozen multiprocessing workers before application imports run."""

import multiprocessing

multiprocessing.freeze_support()
