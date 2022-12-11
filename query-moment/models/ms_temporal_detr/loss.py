import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import List
from einops import rearrange, repeat
from detectron2.config import instantiate
from misc import calc_iou_score_gt

def l1_loss(pred_bds, gt):
    if isinstance(pred_bds, torch.Tensor):
        # B, Nc, _2 = preds.shape
        # B, _2 = gt.shape
        return torch.mean(torch.abs(pred_bds - gt[:, None, :]))
    else:
        loss = 0.0
        for idx, pred_bd in enumerate(pred_bds):
            # NC, _2 = pred.shape
            loss = loss + 0.5 * (
                torch.abs(pred_bd[:, 0] - gt[idx, 0])
                + torch.abs(pred_bd[:, 1] - gt[idx, 1])
            )
        loss /= len(pred_bds)
    return loss


def dist_loss(pred_logits, gt_span, loss_weight=1.0, loss_fn=F.kl_div):
    if isinstance(pred_logits, torch.Tensor):
        B, Nc, _2, Llgt = pred_logits.shape
        expand_gt = repeat(gt_span, "b i llgt -> b nc i llgt", nc=Nc)
        pred_score = torch.softmax(pred_logits, dim=-1)
        return loss_fn(pred_score, expand_gt, reduction="mean") * loss_weight
    else:
        loss = 0.0
        for logits in pred_logits:
            Nc, _2, Llgt = logits.shape
            score = torch.softmax(logits, dim=-1)
            loss += loss_fn(pred_score, expand_gt, reduction="mean")
        return loss * loss_weight

def focal_loss(iou_scores, pred_bds, gt, alpha=2, iou_type="iou"):
    loss = 0.0
    if isinstance(pred_bds, torch.Tensor):
        B, Nc, _2 = pred_bds.shape
        pred_bds_flatten = rearrange(pred_bds, "b nc i -> (b nc) i")
        gt_flatten = repeat(gt, "b i -> (b nc) i", nc=Nc)
        iou_gt_flatten = calc_iou_score_gt(pred_bds_flatten, gt_flatten, type=iou_type)
        iou_gt_flatten[iou_gt_flatten > 0.6] = 1.0
        iou_gt_flatten[iou_gt_flatten < 0.1] = 0.0
        
        iou_scores_flatten = rearrange(iou_scores, "b nc-> (b nc)")
        loss = F.binary_cross_entropy(iou_scores_flatten, iou_gt_flatten, reduction="none")
        loss = loss * ((iou_scores_flatten - iou_gt_flatten) ** alpha)
        loss = torch.mean(loss)
        return loss
    else:
        loss = 0.0
        tot_cand = 0
        for iou_score, pred_bd, cur_gt in zip(iou_scores, pred_bds, gt):
            Nc, _2 = pred_bd.shape
            gt_flatten = repeat(cur_gt, "i -> nc i", nc=Nc)
            iou_gt = calc_iou_score_gt(pred_bd, gt_flatten)
            cur_loss = F.binary_cross_entropy(iou_score, iou_gt, reduction="none")
            cur_loss = cur_loss * ((iou_score - iou_gt) ** alpha)
            loss += cur_loss
            tot_cand += Nc
        return loss / tot_cand