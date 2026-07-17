"""PyTorch ``Dataset`` pitfall rules (SM609–SM610).

LLM-generated data-loading code routinely front-loads work into ``__init__``
(reading every sample into memory) or touches CUDA before DataLoader workers
fork. Both look harmless in a demo and fail on realistic dataset sizes, so
they get their own rules instead of hiding among the generic semantic smells.
"""

from __future__ import annotations

import ast
from typing import Iterable, Iterator

from cleancode.models import FileContext, Severity, Violation, ViolationDetails
from cleancode.rules.base import FunctionNode, Rule


def _base_looks_like_dataset(base: ast.expr) -> bool:
    if isinstance(base, ast.Name):
        return base.id == "Dataset"
    if isinstance(base, ast.Attribute):
        return base.attr == "Dataset"
    return False


def _dataset_classes(tree: ast.Module) -> Iterator[ast.ClassDef]:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and any(_base_looks_like_dataset(base) for base in node.bases):
            yield node


def _find_method(class_def: ast.ClassDef, name: str) -> FunctionNode | None:
    for item in class_def.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == name:
            return item
    return None


def _dataset_methods(class_def: ast.ClassDef, names: tuple[str, ...]) -> Iterator[FunctionNode]:
    for name in names:
        method = _find_method(class_def, name)
        if method is not None:
            yield method


_EAGER_IO_ATTRS = frozenset({"load", "imread", "open"})


def _is_eager_io_call(node: ast.Call) -> bool:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "open"
    if isinstance(func, ast.Attribute):
        return func.attr in _EAGER_IO_ATTRS
    return False


class EagerDatasetLoading(Rule):
    id = "SM609"
    name = "eager-dataset-loading"
    default_severity = Severity.WARNING
    default_options: dict = {}
    description = (
        "Flags file/array loading calls (`np.load`, `open`, `Image.open`, `cv2.imread`, "
        "`torch.load`, ...) inside `__init__` of a `Dataset` subclass — eagerly loading "
        "every sample's payload at construction time defeats lazy loading and can OOM "
        "on realistic dataset sizes."
    )
    guidance = (
        "In a `Dataset.__init__`, store file paths only — load the actual payload "
        "lazily inside `__getitem__`, never eagerly at construction time."
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        for class_def in _dataset_classes(ctx.tree):
            for method in _dataset_methods(class_def, ("__init__",)):
                yield from self._check_init(ctx, class_def, method)

    def _check_init(self, ctx: FileContext, class_def: ast.ClassDef, init: FunctionNode) -> Iterator[Violation]:
        for node in ast.walk(init):
            if isinstance(node, ast.Call) and _is_eager_io_call(node):
                snippet = ast.get_source_segment(ctx.source, node) or "<call>"
                yield self.violation(
                    ctx,
                    node,
                    ViolationDetails(
                        message=f"`{snippet}` loads data eagerly inside `__init__`",
                        suggestion=(
                            "store the file path in `__init__` and load the payload lazily "
                            "in `__getitem__`"
                        ),
                        symbol=f"{class_def.name}.__init__",
                    ),
                )


def _looks_like_device_value(arg: ast.expr) -> bool:
    if isinstance(arg, ast.Constant):
        return isinstance(arg.value, str) and ("cuda" in arg.value or arg.value == "cpu")
    if isinstance(arg, ast.Call):
        return isinstance(arg.func, ast.Attribute) and arg.func.attr == "device"
    return (isinstance(arg, ast.Attribute) and "device" in arg.attr.lower()) or (
        isinstance(arg, ast.Name) and "device" in arg.id.lower()
    )


def _has_device_arg(call: ast.Call) -> bool:
    has_device_keyword = any(keyword.arg == "device" for keyword in call.keywords)
    return has_device_keyword or any(_looks_like_device_value(arg) for arg in call.args)


def _is_device_placement_call(node: ast.Call) -> bool:
    if not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr == "cuda":
        return True
    return node.func.attr == "to" and _has_device_arg(node)


class PrematureDevicePlacement(Rule):
    id = "SM610"
    name = "premature-device-placement"
    default_severity = Severity.WARNING
    default_options: dict = {}
    description = (
        "Flags `.cuda()`/`.to(device=...)` calls inside `__init__` or `__getitem__` of a "
        "`Dataset` subclass — initializing a CUDA context before DataLoader workers fork "
        "corrupts the context across processes, causing deadlocks or segfaults."
    )
    guidance = (
        "Never call `.cuda()`/`.to(device=...)` inside a `Dataset`'s "
        "`__init__`/`__getitem__` — keep tensors on CPU there and move to device in "
        "the training loop."
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        for class_def in _dataset_classes(ctx.tree):
            for method in _dataset_methods(class_def, ("__init__", "__getitem__")):
                yield from self._check_method(ctx, class_def, method)

    def _check_method(
        self, ctx: FileContext, class_def: ast.ClassDef, method: FunctionNode
    ) -> Iterator[Violation]:
        for node in ast.walk(method):
            if isinstance(node, ast.Call) and _is_device_placement_call(node):
                snippet = ast.get_source_segment(ctx.source, node) or "<call>"
                yield self.violation(
                    ctx,
                    node,
                    ViolationDetails(
                        message=f"`{snippet}` places a tensor on-device inside `{method.name}`",
                        suggestion=(
                            "keep tensors on CPU in the Dataset; move to the target device in "
                            "the training loop after the DataLoader yields the batch"
                        ),
                        symbol=f"{class_def.name}.{method.name}",
                    ),
                )
