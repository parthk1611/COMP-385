"""The spatial neural network (CNN): a small U-Net that predicts a whole next-pass burn map.

The per-cell models judge one candidate cell at a time.  This network reads a
96 x 96 map patch around the active perimeter (see `cnn_patches.py`) and
predicts, for every cell, the chance it is newly seen burning at the next pass.
Every training patch is also seen rotated and mirrored (the eight symmetries of
the square) with its arrow channels turned to match, and predictions are
averaged over those eight views.  The loss is cross-entropy over the candidate
cells only.  Trained on the GPU when one is present (`train_cnn.py`).

`cnn_runs` is the same network trained to take long runs seriously: each newly
burning cell counts `1 + far_weight x its distance (km) from the burned area` in
the loss, so cells reached only by a long run weigh more.  `far_weight` 0 is the
plain CNN, rerun beside it so the comparison is like for like.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .cnn_patches import CHANNELS, SIZE, VECTORS
from .contract import SEED


SIMULATOR_CHANNEL = CHANNELS.index("sim_reached_share")
VARIANTS = {"cnn": False, "cnn_hybrid": True, "cnn_runs": False}  # name -> sees the simulator channel
CANDIDATES = [{"width": 32, "epochs": epochs, "learning_rate": 1e-3, "weight_decay": 1e-4, "batch_size": 16} for epochs in [20, 40]]
# each variant's settings; cnn_runs keeps the plain CNN's chosen setting and varies only the long-run weight
VARIANT_CANDIDATES = {"cnn": CANDIDATES, "cnn_hybrid": CANDIDATES, "cnn_runs": [{**CANDIDATES[1], "far_weight": w} for w in [0.0, 1.0, 2.0]]}
DISTANCE_CHANNEL = CHANNELS.index("distance_to_burned")  # stored as km / 6


def apply_symmetry(x, flip: bool, k: int, vectors: list[tuple[int, int]]):
    """Mirror (east-west) and then turn k quarter turns anticlockwise a [batch, channel, east, north] tensor.

    Arrow channels are turned with the map: a mirror changes the sign of the east part, and a quarter turn
    anticlockwise sends (east, north) to (-north, east).
    """
    import torch

    x = x.clone()
    if flip:
        x = torch.flip(x, dims=[2])
        for e, _ in vectors:
            x[:, e] = -x[:, e]
    for _ in range(k):
        x = torch.rot90(x, 1, dims=(2, 3))
        for e, n in vectors:
            east, north = x[:, e].clone(), x[:, n].clone()
            x[:, e], x[:, n] = -north, east
    return x


def symmetries(x, vectors: list[tuple[int, int]]):
    """The eight rotations/mirrors of a patch batch, as (flip, quarter turns, transformed batch)."""
    return [(flip, k, apply_symmetry(x, flip, k, vectors)) for flip in (False, True) for k in range(4)]


def undo(prediction, flip: bool, k: int):
    """Bring a prediction made on a transformed patch back to the original orientation."""
    import torch

    prediction = torch.rot90(prediction, -k, dims=(-2, -1))
    return torch.flip(prediction, dims=[-2]) if flip else prediction


def make_network(channels: int, width: int):
    import torch
    from torch import nn

    def block(a, b):
        return nn.Sequential(nn.Conv2d(a, b, 3, padding=1), nn.BatchNorm2d(b), nn.ReLU(inplace=True), nn.Conv2d(b, b, 3, padding=1), nn.BatchNorm2d(b), nn.ReLU(inplace=True))

    class UNet(nn.Module):
        """A small U-Net: three resolutions (375 m, 750 m, 1.5 km), so a cell sees about 20 km of context."""

        def __init__(self):
            super().__init__()
            self.down1, self.down2, self.down3 = block(channels, width), block(width, 2 * width), block(2 * width, 3 * width)
            self.up2, self.up1 = block(5 * width, 2 * width), block(3 * width, width)
            self.out = nn.Conv2d(width, 1, 1)
            self.pool = nn.MaxPool2d(2)

        def forward(self, x):
            a = self.down1(x)
            b = self.down2(self.pool(a))
            c = self.down3(self.pool(b))
            up = nn.functional.interpolate(c, scale_factor=2, mode="bilinear", align_corners=False)
            b = self.up2(torch.cat([up, b], dim=1))
            up = nn.functional.interpolate(b, scale_factor=2, mode="bilinear", align_corners=False)
            return self.out(self.up1(torch.cat([up, a], dim=1)))[:, 0]

    return UNet()


def _channels(hybrid: bool) -> list[int]:
    return [c for c in range(len(CHANNELS)) if hybrid or c != SIMULATOR_CHANNEL]


def fit(x: np.ndarray, y: np.ndarray, mask: np.ndarray, params: dict, hybrid: bool, device):
    import torch

    torch.manual_seed(SEED)
    rng = np.random.default_rng(SEED)
    channels = _channels(hybrid)
    vectors = [(channels.index(CHANNELS.index(e)), channels.index(CHANNELS.index(n))) for e, n in VECTORS]
    far_weight, distance = params.get("far_weight", 0.0), channels.index(DISTANCE_CHANNEL)
    network = make_network(len(channels), params["width"]).to(device)
    optimiser = torch.optim.AdamW(network.parameters(), lr=params["learning_rate"], weight_decay=params["weight_decay"])
    steps_per_epoch = math.ceil(len(x) / params["batch_size"])
    schedule = torch.optim.lr_scheduler.OneCycleLR(optimiser, max_lr=params["learning_rate"], total_steps=params["epochs"] * steps_per_epoch)
    network.train()
    for _ in range(params["epochs"]):
        order = rng.permutation(len(x))
        for start in range(0, len(x), params["batch_size"]):
            batch = order[start : start + params["batch_size"]]
            xb = torch.from_numpy(x[batch][:, channels].astype(np.float32)).to(device)
            yb = torch.from_numpy(y[batch].astype(np.float32)).to(device)
            mb = torch.from_numpy(mask[batch]).to(device)
            choice = int(rng.integers(8))
            flip, k = bool(choice // 4), choice % 4
            xb = apply_symmetry(xb, flip, k, vectors)
            yb, mb = _transform(yb, flip, k), _transform(mb, flip, k)
            logits = network(xb)
            # newly burning cells far from the burned area weigh more when far_weight > 0 (a long run missed costs more)
            weight = 1.0 + far_weight * (xb[:, distance] * 6.0) * yb
            loss = torch.nn.functional.binary_cross_entropy_with_logits(logits[mb], yb[mb], weight=weight[mb]) if mb.any() else logits.sum() * 0
            optimiser.zero_grad()
            loss.backward()
            optimiser.step()
            schedule.step()
    return network.eval(), channels, vectors


def _transform(t, flip: bool, k: int):
    import torch

    t = torch.flip(t, dims=[-2]) if flip else t
    return torch.rot90(t, k, dims=(-2, -1))


def predict(network, channels, vectors, x: np.ndarray, device, batch_size: int = 32) -> np.ndarray:
    """Probability maps averaged over the eight symmetries."""
    import torch

    out = np.zeros((len(x), SIZE, SIZE), dtype=np.float32)
    with torch.no_grad():
        for start in range(0, len(x), batch_size):
            xb = torch.from_numpy(x[start : start + batch_size][:, channels].astype(np.float32)).to(device)
            total = torch.zeros(xb.shape[0], SIZE, SIZE, device=device)
            for flip, k, view in symmetries(xb, vectors):
                total += undo(torch.sigmoid(network(view)), flip, k)
            out[start : start + batch_size] = (total / 8).cpu().numpy()
    return out


def row_probabilities(maps: np.ndarray, patch_ids: np.ndarray, index: pd.DataFrame) -> pd.DataFrame:
    """Each table row's probability from its step's map; rows outside the patch get zero."""
    rows = index[index.patch.isin(patch_ids)].copy()
    position = {p: i for i, p in enumerate(patch_ids)}
    inside = rows.px.to_numpy() >= 0
    probability = np.zeros(len(rows), dtype=np.float32)
    local = rows.patch.map(position).to_numpy()
    probability[inside] = maps[local[inside], rows.px.to_numpy()[inside], rows.py.to_numpy()[inside]]
    rows["p"] = probability
    return rows[["fire_id", "observation", "cell", "p"]]
