import torch
import torch.nn as nn
import pytorch_lightning as pl
from pytorch_lightning.utilities.seed import seed_everything
from detectron2.config import instantiate
from kn_util.config import dispatch_arguments_to_cfgs
from torchmetrics import Metric
from misc import calc_iou_score_gt
from einops import repeat
from kn_util.general import registry, get_logger
from pprint import pformat
import wandb

class AverageMeter(Metric):

    def __init__(self):
        super().__init__()
        self.add_state("sum", default=torch.tensor(0.0), dist_reduce_fx="sum")
        self.add_state("n", default=torch.tensor(0.0), dist_reduce_fx="sum")

    def update(self, val):
        self.sum += val.detach()
        self.n += 1

    def compute(self):
        return self.sum / self.n


class RankMIoUAboveN(Metric):

    def __init__(self, m, n) -> None:
        super().__init__()
        self.m = m
        self.n = n
        self.add_state("hit", default=torch.tensor(0.0), dist_reduce_fx="sum")
        self.add_state(
            "num_sample", default=torch.tensor(0.0), dist_reduce_fx="sum")

    def update(self, pred_bds, gt):
        B = len(pred_bds)
        pred_bds_batch = pred_bds
        gt_batch = gt
        for i in range(B):
            pred_bds = pred_bds_batch[i]
            gt = gt_batch[i]
            Nc, _2 = pred_bds.shape
            expand_gt = repeat(gt, "i -> nc i", nc=Nc)
            ious = calc_iou_score_gt(pred_bds, expand_gt)
            is_hit = torch.sum((ious >= self.n).long()) >= self.m
            self.hit += is_hit.float()
            self.num_sample += 1

    def compute(self):
        return self.hit / self.num_sample


class MomentRetrievalModule(pl.LightningModule):

    def __init__(self, cfg) -> None:
        super().__init__()
        self.save_hyperparameters()
        self.net = instantiate(cfg.model)
        self.metrics = nn.ModuleList(self.build_metrics())
        
    def build_metrics(self):
        cfg = self.cfg
        metrics = dict()
        metrics["train"] = {k: AverageMeter() for k in cfg.loss_keys}
        for m in [1, 5]:
            for n in [0.3, 0.5, 0.7]:
                name = f"Rank{m}@IoU={n:.1f}"
                metrics["val"][name] = RankMIoUAboveN(m, n)
                metrics["test"][name] = RankMIoUAboveN(m, n)
        return metrics
    
    def update_metric(self, outputs, domain):
        if domain == "train":
            metrics = self.metrics["train"]
            for k in outputs:
                metrics[k].update(outputs[k])
        else:
            metrics = self.metrics[domain]
            for metric in self.metrics.values():
                if isinstance(metric, RankMIoUAboveN):
                    metric.update(outputs["pred_bds"], outputs["gt"])
        
    def log_metric(self, domain):
        metrics = self.metrics[domain]
        ret_dict = dict()
        for name, metric in metrics.items():
            ret_dict[f"{domain}/{name}"] = 
            log.info(pformat())
            metric.reset()

    def forward(self, *args, **kwargs):
        return self.net(*args, **kwargs)

    def on_train_epoch_start(self):
        seed = self.cfg.G.seed
        seed_everything(seed + self.current_epoch)

    def training_step(self, batch, batch_idx):
        bag = dict()
        bag.update(batch)
        output = self.net(**bag)
        bag.update(output)
        losses = self.net.compute_loss(**bag)

        return losses

    def training_step_end(self, losses):
        self.train_epoch_loss.update(losses["loss"])

    def training_epoch_end(self, outputs):
        epoch_loss = self.train_epoch_loss.compute()
        self.log("train/epoch_loss", epoch_loss)
        # log.info(f"train/epoch_loss: \t{epoch_loss}")
        self.train_epoch_loss.reset()

    def validation_step(self, batch, batch_idx):
        with torch.no_grad():
            bag = dict()
            bag.update(batch)
            output = self.net(**bag)
            bag.update(output)
            inference_output = self.net.inference(**bag)

        return inference_output

    def validation_step_end(self, *args, **kwargs):
        pass

    def test_step(self, batch, batch_idx):
        return self.validation_step(self, batch, batch_idx)

def train_one_epoch(model, dataloader, optimizer):
    pass