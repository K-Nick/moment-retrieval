import torch
import torch.nn.functional as F


def bce_rescale_loss(config, logits_visual, logits_iou, iou_mask_map, gt_maps, gt_times):
    T = gt_maps.shape[-1]
    joint_prob = torch.sigmoid(logits_visual[:, :3, :])
    gt_p = gt_maps[:, :3, :]
    loss = F.binary_cross_entropy_with_logits(logits_visual[:, :3, :], gt_p,
                                              reduction='none') * (joint_prob - gt_p) * (joint_prob - gt_p)

    reg_mask = (gt_maps[:, 0:1, :T, None] >= 0.4) * (gt_maps[:, 1:2, None, :] >= 0.4)
    gt_tmp = torch.cat((gt_maps[:, 3:4, :T, None].repeat(1, 1, 1, T), gt_maps[:, 4:5, None, :].repeat(1, 1, T, 1)), 1)
    loss_reg = (torch.abs(logits_iou[:, :2, :, :] - gt_tmp) * reg_mask).sum((2, 3)) / reg_mask.sum((2, 3))

    idxs = torch.arange(T, device=logits_iou.device)
    s_e_idx = torch.cat((idxs[None, None, :T, None].repeat(1, 1, 1, T), idxs[None, None, None, :].repeat(1, 1, T, 1)),
                        1)
    s_e_time = (s_e_idx + logits_iou[:, :2, :, :]).clone().detach()

    iou = torch.clamp(torch.min(gt_times[:, 1][:, None, None], s_e_time[:, 1, :, :]) -
                      torch.max(gt_times[:, 0][:, None, None], s_e_time[:, 0, :, :]),
                      min=0.0000000001) / torch.clamp(torch.max(gt_times[:, 1][:, None, None], s_e_time[:, 1, :, :]) -
                                                      torch.min(gt_times[:, 0][:, None, None], s_e_time[:, 0, :, :]),
                                                      min=0.0000001)

    temp = (s_e_time[:, 0, :, :] < s_e_time[:, 1, :, :]) * iou_mask_map[None, :, :]
    # iou[iou > 0.7] = 1.
    iou[iou < 0.5] = 0.
    loss_iou = (F.binary_cross_entropy_with_logits(logits_iou[:, 2, :, :], iou, reduction='none') * temp *
                torch.pow(torch.sigmoid(logits_iou[:, 2, :, :]) - iou, 2)).sum((1, 2)) / temp.sum((1, 2))

    loss_value = config.w_stage_loss * loss.sum(
        -1).mean() + config.w_reg_loss * loss_reg.mean() + config.w_iou_loss * loss_iou.mean()

    return loss_value, joint_prob, torch.sigmoid(logits_iou[:, 2, :, :]) * temp, s_e_time
