"""Readable array windowing helpers, the way SL401 wants them written."""


def rolling_windows(series, window_size):
    windows = []
    last_start = len(series) - window_size
    for start in range(last_start + 1):
        stop = start + window_size
        windows.append(series[start:stop])
    return windows


def latest_reading(readings):
    # sensors occasionally deliver an empty batch after a reconnect
    if not readings:
        return None
    return readings[-1]
