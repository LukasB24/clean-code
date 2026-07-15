"""PyTorch dataset that lazily loads spectrogram arrays from disk."""

import os

import numpy as np
import torch

MIN_MAX_NORMALIZATION_EPSILON = 1e-8


class SpectrogramDataset(torch.utils.data.Dataset):
    def __init__(self, data_dir: str, apply_normalization: bool = True) -> None:
        self.data_dir = data_dir
        self.apply_normalization = apply_normalization
        self.file_names = [name for name in os.listdir(data_dir) if name.endswith(".npy")]

    def __len__(self) -> int:
        return len(self.file_names)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, int]:
        file_name = self.file_names[idx]
        spectrogram = self._load_spectrogram(file_name)
        label = 1 if "anomaly" in file_name else 0
        return spectrogram, label

    def _load_spectrogram(self, file_name: str) -> torch.Tensor:
        file_path = os.path.join(self.data_dir, file_name)
        array = np.load(file_path)
        if self.apply_normalization:
            array = self._min_max_normalize(array)
        return torch.tensor(array, dtype=torch.float32)

    @staticmethod
    def _min_max_normalize(array: np.ndarray) -> np.ndarray:
        minimum = np.min(array)
        maximum = np.max(array)
        return (array - minimum) / (maximum - minimum + MIN_MAX_NORMALIZATION_EPSILON)
