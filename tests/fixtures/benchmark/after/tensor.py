"""Windowed tensor extraction, with each slicing step named."""


def transform(tensor, boundaries, frame_index):
    start = boundaries[frame_index + 1]
    stop = boundaries[frame_index + 2]

    expanded = tensor.unsqueeze(1)
    window = expanded[:, :, start:stop:2, :].flip(dims=[-1])

    frame = tensor[frame_index]
    first_row = frame[0]
    last_value = first_row[-1]

    return window, last_value
