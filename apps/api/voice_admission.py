"""Bind reviewed GPU entry points only during the optional main voice application's lifetime."""

import importlib
import logging

from src.application.services.gpu_admission import bind, guard_gpu, unbind

LOGGER = logging.getLogger(__name__)
TARGETS = (
    ("apps.api.services.llama_gateway", "LlamaGateway", "complete"),
    ("apps.api.services.llama_gateway", "LlamaGateway", "_count_input_tokens"),
    ("apps.api.services.llama_gateway", "LlamaGateway", "_select_auto_preset"),
    ("src.infrastructure.inference.llama_adapter", "LlamaInferenceAdapter", "complete"),
    (
        "src.infrastructure.inference.coding_reasoning",
        "CodingReasoningAdapter",
        "complete",
    ),
    (
        "src.infrastructure.inference.structured_excerpt_adapter",
        "StructuredExcerptAdapter",
        "complete",
    ),
    (
        "src.infrastructure.inference.structured_profile",
        "StructuredProfileAdapter",
        "complete",
    ),
    (
        "src.infrastructure.inference.structured_profile",
        "StructuredProfileAdapter",
        "_complete_native",
    ),
    (
        "src.infrastructure.inference.core_vision_chat",
        "CoreVisionChatAdapter",
        "complete_image",
    ),
    ("apps.api.services.vision_ocr", None, "transcribe_image"),
    ("apps.api.services.files", None, "transcribe_image"),
)


class ManagedGPUCalls:
    """Install reversible guards around exact existing class/function entry points without source edits."""

    def __init__(self, admission):
        """Retain an owning coordinator and exact original callables for verified shutdown restoration."""
        self.admission, self.bound = admission, []

    def start(self):
        """Guard every declared native path before admitting main-app requests or voice preparation."""
        bind(self.admission)
        try:
            for module_name, class_name, method in TARGETS:
                module = importlib.import_module(module_name)
                owner = getattr(module, class_name) if class_name else module
                original = getattr(owner, method)
                wrapped = guard_gpu(original)
                setattr(owner, method, wrapped)
                self.bound.append((owner, method, original, wrapped))
        except BaseException:
            self.close()
            raise
        LOGGER.info("voice_managed_gpu_paths_bound count=%d", len(self.bound))

    def close(self):
        """Restore only exact wrappers installed by this lifetime after owned work has joined."""
        for owner, method, original, wrapped in reversed(self.bound):
            if getattr(owner, method) is not wrapped:
                self.admission.quarantine()
                raise RuntimeError("gpu_guard_binding_changed")
            setattr(owner, method, original)
        self.bound.clear()
        unbind(self.admission)
        LOGGER.info("voice_managed_gpu_paths_restored")
