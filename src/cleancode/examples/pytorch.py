"""BAD/GOOD examples for the PyTorch `Dataset` pitfall rules (SM609-SM610)."""

from __future__ import annotations

from cleancode.examples._types import Example

EXAMPLES: dict[str, Example] = {
    "SM609": Example(
        bad=(
            "class ImageDataset(Dataset):\n"
            "    def __init__(self, paths):\n"
            "        self.images = [Image.open(path) for path in paths]\n"
        ),
        good=(
            "class ImageDataset(Dataset):\n"
            "    def __init__(self, paths):\n"
            "        self.paths = paths\n"
            "\n"
            "    def __getitem__(self, index):\n"
            "        return Image.open(self.paths[index])\n"
        ),
        note=None,
    ),
    "SM610": Example(
        bad=(
            "class TensorDataset(Dataset):\n"
            "    def __init__(self, paths):\n"
            "        self.paths = paths\n"
            "\n"
            "    def __getitem__(self, index):\n"
            "        tensor = load_tensor(self.paths[index])\n"
            "        return tensor.cuda()\n"
        ),
        good=(
            "class TensorDataset(Dataset):\n"
            "    def __init__(self, paths):\n"
            "        self.paths = paths\n"
            "\n"
            "    def __getitem__(self, index):\n"
            "        return load_tensor(self.paths[index])\n"
        ),
        note="Move tensors to device in the training loop, after the DataLoader yields the batch.",
    ),
}
