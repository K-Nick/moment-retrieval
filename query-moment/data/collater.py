from kn_util.data import (
    merge_list_to_tensor,
    fix_tensor_to_float32,
    collect_features_from_sample_list,
)
from .processor import apply_processors
from .processor import test_pipeline_signal as _signal
import copy
from typing import Dict, List, Any
import numpy as np
from kn_util.general import registry
from kn_util.debug import SignalContext
from collections import OrderedDict


@registry.register_collater("simple")
class SimpleCollater:
    """collect feature from sample list into dict of tensor"""

    def __init__(self, cfg, processors, is_train) -> None:
        self.cfg = cfg
        self.processors = processors
        self.is_train = is_train

    def get_feature_dict(self, batch) -> Dict[str, List[np.ndarray]]:
        return collect_features_from_sample_list(batch)

    def __call__(self, _batch):
        batch = copy.deepcopy(_batch)
        batch = apply_processors(batch, self.processors)
        feature_dict = self.get_feature_dict(batch)
        return fix_tensor_to_float32(merge_list_to_tensor(feature_dict))
