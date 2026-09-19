"""PyTorch EfficientTransUNet (ported from MIAS Keras efficienttransUNet.py)."""
from __future__ import annotations

import math
from typing import Literal

import torch
import torch.nn as nn
import torch.nn.functional as F

Variant = Literal["B0", "B1", "B2", "B3", "B4"]

VARIANT_CFG = {
    "B0": dict(width_coefficient=1.0, depth_coefficient=1.0, drop_connect_rate=0.2),
    "B1": dict(width_coefficient=1.0, depth_coefficient=1.1, drop_connect_rate=0.2),
    "B2": dict(width_coefficient=1.1, depth_coefficient=1.2, drop_connect_rate=0.3),
    "B3": dict(width_coefficient=1.2, depth_coefficient=1.4, drop_connect_rate=0.3),
    "B4": dict(width_coefficient=1.4, depth_coefficient=1.8, drop_connect_rate=0.4),
}


def round_filters(filters: int, multiplier: float) -> int:
    depth_divisor = 8
    min_depth = depth_divisor
    filters = filters * multiplier
    new_filters = max(min_depth, int(filters + depth_divisor / 2) // depth_divisor * depth_divisor)
    if new_filters < 0.9 * filters:
        new_filters += depth_divisor
    return int(new_filters)


def round_repeats(repeats: int, multiplier: float) -> int:
    if not multiplier:
        return repeats
    return int(math.ceil(multiplier * repeats))


class SEBlock(nn.Module):
    def __init__(self, channels: int, ratio: float = 0.25):
        super().__init__()
        reduced = max(1, int(channels * ratio))
        self.pool = nn.AdaptiveAvgPool2d(1)
        self.reduce = nn.Conv2d(channels, reduced, 1)
        self.expand = nn.Conv2d(reduced, channels, 1)

    def forward(self, x):
        b = self.pool(x)
        b = F.silu(self.reduce(b))
        b = torch.sigmoid(self.expand(b))
        return x * b


class MBConv(nn.Module):
    def __init__(self, in_ch: int, out_ch: int, expansion: int, stride: int, k: int, drop_connect: float):
        super().__init__()
        self.stride = stride
        self.in_ch = in_ch
        self.out_ch = out_ch
        self.drop_connect = drop_connect
        mid = in_ch * expansion
        self.expand = nn.Conv2d(in_ch, mid, 1, bias=False) if expansion != 1 else nn.Identity()
        self.bn1 = nn.BatchNorm2d(mid if expansion != 1 else in_ch, eps=1e-6)
        self.dw = nn.Conv2d(mid if expansion != 1 else in_ch, mid if expansion != 1 else in_ch, k, stride=stride, padding=k // 2, groups=mid if expansion != 1 else in_ch, bias=False)
        self.bn2 = nn.BatchNorm2d(mid if expansion != 1 else in_ch, eps=1e-6)
        self.se = SEBlock(mid if expansion != 1 else in_ch)
        self.project = nn.Conv2d(mid if expansion != 1 else in_ch, out_ch, 1, bias=False)
        self.bn3 = nn.BatchNorm2d(out_ch, eps=1e-6)
        self.expansion = expansion

    def forward(self, x):
        residual = x
        if self.expansion != 1:
            x = F.silu(self.bn1(self.expand(x)))
        else:
            x = F.silu(self.bn1(x))
        x = F.silu(self.bn2(self.dw(x)))
        x = self.se(x)
        x = F.silu(x)
        x = self.bn3(self.project(x))
        if self.stride == 1 and self.in_ch == self.out_ch:
            if self.training and self.drop_connect > 0:
                keep = 1.0 - self.drop_connect
                mask = torch.empty(x.size(0), 1, 1, 1, device=x.device, dtype=x.dtype).bernoulli_(keep) / keep
                x = x * mask
            x = x + residual
        return x


class MBConvBlock(nn.Module):
    def __init__(self, in_ch, out_ch, n_layers, stride, expansion, k, drop_connect):
        super().__init__()
        layers = []
        for i in range(n_layers):
            layers.append(
                MBConv(
                    in_ch if i == 0 else out_ch,
                    out_ch,
                    expansion,
                    stride if i == 0 else 1,
                    k,
                    drop_connect,
                )
            )
        self.net = nn.Sequential(*layers)

    def forward(self, x):
        return self.net(x)


class TransformerBlock(nn.Module):
    """Matches Keras: LN -> MHA(residual) -> LN -> MLP(residual).

    Uses standard MultiheadAttention (embed=256, heads=4 => head_dim=64).
    """

    def __init__(self, dim: int = 256, num_heads: int = 4, mlp_dim: int = 512, dropout: float = 0.1):
        super().__init__()
        self.ln1 = nn.LayerNorm(dim, eps=1e-6)
        self.attn = nn.MultiheadAttention(dim, num_heads, dropout=dropout, batch_first=True)
        self.ln2 = nn.LayerNorm(dim, eps=1e-6)
        self.mlp = nn.Sequential(
            nn.Linear(dim, mlp_dim),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(mlp_dim, dim),
            nn.Dropout(dropout),
        )

    def forward(self, x):
        h = self.ln1(x)
        attn_out, _ = self.attn(h, h, h, need_weights=False)
        x = x + attn_out
        x = x + self.mlp(self.ln2(x))
        return x


class EfficientTransUNet(nn.Module):
    def __init__(
        self,
        variant: Variant = "B0",
        in_channels: int = 1,
        num_classes: int = 1,
        transformer_layers: int = 8,
        dropout: float = 0.1,
        projection_dim: int = 256,
        num_heads: int = 4,
    ):
        super().__init__()
        cfg = VARIANT_CFG[variant]
        w = cfg["width_coefficient"]
        d = cfg["depth_coefficient"]
        drop_connect = cfg["drop_connect_rate"]
        self.variant = variant

        c32 = round_filters(32, w)
        c16 = round_filters(16, w)
        c24 = round_filters(24, w)
        c40 = round_filters(40, w)
        c80 = round_filters(80, w)
        c112 = round_filters(112, w)

        self.stem = nn.Sequential(
            nn.Conv2d(in_channels, c32, 3, stride=2, padding=1, bias=True),
            nn.BatchNorm2d(c32, eps=1e-6),
        )
        self.block1 = MBConvBlock(c32, c16, round_repeats(1, d), 1, 1, 3, drop_connect)
        self.block2 = MBConvBlock(c16, c24, round_repeats(2, d), 2, 6, 3, drop_connect)
        self.block3 = MBConvBlock(c24, c40, round_repeats(2, d), 2, 6, 5, drop_connect)
        self.block4 = MBConvBlock(c40, c80, round_repeats(3, d), 2, 6, 3, drop_connect)
        self.block5 = MBConvBlock(c80, c112, round_repeats(3, d), 1, 6, 5, drop_connect)
        self.bn_bridge = nn.BatchNorm2d(c112, eps=1e-6)

        self.to_tokens = nn.Sequential(
            nn.Conv2d(c112, projection_dim, 1, bias=False),
            nn.ReLU(inplace=True),
            nn.BatchNorm2d(projection_dim, eps=1e-6),
        )
        self.num_patches = 16 * 16
        self.pos_embed = nn.Parameter(torch.zeros(1, self.num_patches, projection_dim))
        nn.init.trunc_normal_(self.pos_embed, std=0.02)
        self.transformers = nn.ModuleList(
            [TransformerBlock(projection_dim, num_heads, projection_dim * 2, dropout) for _ in range(transformer_layers)]
        )
        self.ln_out = nn.LayerNorm(projection_dim, eps=1e-6)

        self.dec_conv0 = nn.Sequential(
            nn.Conv2d(projection_dim, 256, 3, padding=1, bias=False),
            nn.ReLU(inplace=True),
            nn.BatchNorm2d(256, eps=1e-6),
        )
        self.dec1 = nn.Sequential(
            nn.Conv2d(256 + c40, 128, 3, padding=1, bias=False),
            nn.ReLU(inplace=True),
            nn.BatchNorm2d(128, eps=1e-6),
        )
        self.dec2 = nn.Sequential(
            nn.Conv2d(128 + c24, 64, 3, padding=1, bias=False),
            nn.ReLU(inplace=True),
            nn.BatchNorm2d(64, eps=1e-6),
        )
        self.dec3 = nn.Sequential(
            nn.Conv2d(64 + c16, 64, 3, padding=1, bias=False),
            nn.ReLU(inplace=True),
            nn.BatchNorm2d(64, eps=1e-6),
        )
        self.dec4 = nn.Sequential(
            nn.Conv2d(64, 64, 3, padding=1, bias=False),
            nn.ReLU(inplace=True),
            nn.BatchNorm2d(64, eps=1e-6),
        )
        self.drop = nn.Dropout(dropout)
        # logits (no sigmoid) for BCEWithLogits
        self.head = nn.Conv2d(64, num_classes, 1)

        self.skip_c40 = c40
        self.skip_c24 = c24
        self.skip_c16 = c16

    def forward(self, x):
        # x: NCHW
        s = self.stem(x)  # /2
        b1 = self.block1(s)
        b2 = self.block2(b1)
        b3 = self.block3(b2)
        b4 = self.block4(b3)
        b5 = self.bn_bridge(self.block5(b4))  # 16x16

        tok = self.to_tokens(b5)  # B,256,16,16
        B, C, H, W = tok.shape
        tokens = tok.flatten(2).transpose(1, 2)  # B,256,C
        tokens = tokens + self.pos_embed
        for blk in self.transformers:
            tokens = blk(tokens)
        tokens = self.ln_out(tokens)
        feat = tokens.transpose(1, 2).reshape(B, C, H, W)
        feat = self.dec_conv0(feat)

        u1 = F.interpolate(feat, scale_factor=2, mode="nearest")
        d1 = self.dec1(torch.cat([u1, b3], dim=1))
        u2 = F.interpolate(d1, scale_factor=2, mode="nearest")
        d2 = self.dec2(self.drop(torch.cat([u2, b2], dim=1)))
        u3 = F.interpolate(d2, scale_factor=2, mode="nearest")
        d3 = self.dec3(self.drop(torch.cat([u3, b1], dim=1)))
        u4 = F.interpolate(d3, scale_factor=2, mode="nearest")
        d4 = self.dec4(u4)
        return self.head(d4)


def build_efficient_transunet(variant: str = "B0") -> EfficientTransUNet:
    variant = variant.upper()
    if variant not in VARIANT_CFG:
        raise ValueError(f"Unknown variant {variant}")
    return EfficientTransUNet(variant=variant)  # type: ignore[arg-type]
