import sys
import os.path as osp
import copy
from kn_util.debug import SignalContext

sys.path.insert(0, osp.join(osp.dirname(__file__), "../.."))
from torch.utils.data import (
    SequentialSampler,
    RandomSampler,
    DistributedSampler,
    DataLoader,
)
from data.processor import build_processors, apply_processors
from kn_util.general import global_registry, get_logger
from kn_util.debug import explore_content

log = get_logger(__name__)
_signal = "_TEST_PIPELINE_SIGNAL"


class BaseDataModule:
    def __init__(self, cfg):
        self.cfg = cfg
        self.load_data()
        self.preprocess()
        self.build_dataloaders()

    def load_data(self):
        """to be implemented in sub-class"""
        self.dataset = dict()

    def preprocess(self):
        if not hasattr(self.cfg.data, "pre_processors"):
            return
        self.pre_processor = build_processors(self.cfg.data.pre_processors)

        for domain in ["train", "val", "test"]:
            dataset = self.datasets[domain]

            if domain != "train":
                global_registry.set_object(_signal, False)

            with SignalContext(_signal, self.cfg.G.debug and domain == "train"):
                self.datasets[domain] = apply_processors(
                    dataset,
                    self.pre_processor,
                    tqdm_args=dict(desc=f"preprocess {domain}", total=len(dataset)),
                )

    def _build_sampler(self, domain):
        if domain == "train":
            if self.cfg.get("ddp", False):
                return DistributedSampler(self.datasets[domain])
            else:
                return RandomSampler(self.datasets[domain])
        else:
            return SequentialSampler(self.datasets[domain])

    def build_dataloaders(self):
        cfg = self.cfg
        processors = build_processors(cfg.data.processors)
        self.dataloaders = dict()
        for domain in ["train", "val", "test"]:
            collater = global_registry.build_collater(
                cfg.data.collater,
                cfg=cfg,
                processors=processors,
                is_train=(domain == "train"),
            )
            sampler = self._build_sampler(domain)
            self.dataloaders[domain] = DataLoader(
                self.datasets[domain],
                batch_size=cfg.train.batch_size,
                sampler=sampler,
                prefetch_factor=cfg.train.prefetch_factor,
                num_workers=cfg.train.num_workers,
                collate_fn=collater,
            )

    def get_dataloader(self, domain):
        return self.dataloaders[domain]
