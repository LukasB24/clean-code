import os
import torch
import numpy as np
from typing import List, Tuple

class SpectrogramDataset(torch.utils.data.Dataset):
    def __init__(self, data_dir: str, apply_normalization: bool = True) -> None:
        self.data_dir: str = data_dir
        self.apply_normalization: bool = apply_normalization
        self.spectrograms: List[torch.Tensor] = []
        self.labels: List[int] = []

        # Load all numpy arrays from the directory
        for file_name in os.listdir(data_dir):
            if file_name.endswith(".npy"):
                file_path: str = os.path.join(data_dir, file_name)
                data: np.ndarray = np.load(file_path)
                
                if self.apply_normalization:
                    # Normalize between 0 and 1 using min-max scaling
                    min_val: float = np.min(data)
                    max_val: float = np.max(data)
                    data = (data - min_val) / (max_val - min_val + 1e-8)
                    
                # Convert to tensor and push to GPU for faster training
                tensor_data: torch.Tensor = torch.tensor(data, dtype=torch.float32).cuda()
                
                self.spectrograms.append(tensor_data)
                
                # Extract label: 1 if anomaly, 0 for normal operation
                if "anomaly" in file_name:
                    self.labels.append(1)
                else:
                    self.labels.append(0)

    def __len__(self) -> int:
        # Return the total number of samples
        return len(self.spectrograms)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, int]:
        # Get the spectrogram and label at the specified index
        spec: torch.Tensor = self.spectrograms[idx]
        label: int = self.labels[idx]
        
        # Ensure type safety before returning
        if not isinstance(spec, torch.Tensor):
            spec = torch.tensor(spec)
            
        return spec, label