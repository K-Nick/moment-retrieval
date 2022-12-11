import torch
from torchvision.ops import batched_nms
from einops import repeat, rearrange
import numpy as np

def format_str(v, decimals=4):
    if isinstance(v, (float, np.float_)):
        v = np.round(v ,decimals=decimals)
        return str(v)
    else:
        return str(v)

def dict2str(cur_dict, ordered_keys=None, keep_unordered=True):
    if ordered_keys is None:
        return "\t".join([k + " " + format_str(v) for k,v in cur_dict.items()])
    else:
        ordered = [k + " " + format_str(cur_dict[k]) for k in ordered_keys]
        if keep_unordered:
            unordered = [k + " " + format_str(v) for k,v in cur_dict.items()]
            outputs = ordered
        else:
            outputs = ordered
        return "\t".join(outputs)

def inverse_sigmoid(x, eps=1e-5):
    x = x.clamp(min=0, max=1)
    x1 = x.clamp(min=eps)
    x2 = (1 - x).clamp(min=eps)
    return torch.log(x1 / x2)


def nms(pred_bds, scores, batch_idxs, iou_threshold):
    B, _2 = pred_bds.shape

    zero_pad = torch.zeros(pred_bds.shape[:1], dtype=torch.float32, device=pred_bds.device)
    one_pad = zero_pad + 1
    boxxes = torch.stack([pred_bds[:, 0], zero_pad, pred_bds[:, 1], one_pad], dim=-1)
    boxxes_flatten = boxxes
    scores_flatten = scores

    nms_indices = batched_nms(boxxes_flatten, scores_flatten, batch_idxs, iou_threshold)
    nms_pred_bds_flatten = boxxes_flatten[nms_indices][:, (0,2)]
    nms_scores_flatten = scores_flatten[nms_indices]
    nms_idxs = batch_idxs[nms_indices]

    nms_pred_bds = []
    nms_scores = []
    for b in range(torch.max(batch_idxs).item() + 1):
        cur_batch_indices = (nms_idxs == b)
        nms_pred_bds.append(nms_pred_bds_flatten[cur_batch_indices])
        nms_scores.append(nms_scores_flatten[cur_batch_indices])

    return nms_pred_bds, nms_scores


@torch.no_grad()
def calc_iou_score_gt(pred_bds, gt, type="iou"):
    """make sure the range between [0, 1) to make loss function happy"""
    min_ed = torch.minimum(pred_bds[:, 1], gt[:, 1])
    max_ed = torch.maximum(pred_bds[:, 1], gt[:, 1])
    min_st = torch.minimum(pred_bds[:, 0], gt[:, 0])
    max_st = torch.maximum(pred_bds[:, 0], gt[:, 0])

    I = torch.maximum(min_ed - max_st, torch.zeros_like(min_ed, dtype=torch.float, device=pred_bds.device))
    area_pred = pred_bds[:, 1] - pred_bds[:, 0]
    area_gt = gt[:, 1] - gt[:, 0]
    U = area_pred + area_gt - I
    Ac = max_ed - min_st

    iou = I / U

    if type == "iou":
        return iou
    elif type == "giou":
        return 0.5 * (iou + U / Ac)
    else:
        raise NotImplementedError()


def cw2se(cw):
    se = torch.zeros_like(cw)
    se[..., 0] = cw[..., 0] - cw[..., 1] / 2
    se[..., 0][se[..., 0] < 0.0] = 0.0
    se[..., 1] = cw[..., 0] + cw[..., 1] / 2
    se[..., 1][se[..., 1] > 1.0] = 1.0

    # se[(se[..., 0] < 0.0) | (se[..., 1] > 1.0)] = 0.0

    return se