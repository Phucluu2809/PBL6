"""Compact CNN encoder and cosine enrollment."""

import torch
from torch import nn
from torch.nn import functional as F


class OdorEncoder(nn.Module):
    def __init__(self, classes):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv1d(6, 16, kernel_size=7, padding=3), nn.ReLU(),
            nn.AvgPool1d(2),
            nn.Conv1d(16, 24, kernel_size=5, padding=2), nn.ReLU(),
            nn.AdaptiveAvgPool1d(4), nn.Flatten(),
            nn.Linear(24 * 4, 16),
        )
        self.classifier = nn.Linear(16, classes, bias=False)

    def encode(self, x):
        return F.normalize(self.features(x), dim=1)

    def forward(self, x):
        return 12 * (self.encode(x) @ F.normalize(self.classifier.weight, dim=1).T)


class ResidualBlock(nn.Module):
    def __init__(self, in_channels, out_channels, kernel, stride):
        super().__init__()
        self.body = nn.Sequential(
            nn.Conv1d(in_channels, out_channels, kernel, stride, kernel // 2, bias=False),
            nn.GroupNorm(8, out_channels), nn.GELU(),
            nn.Conv1d(out_channels, out_channels, kernel, padding=kernel // 2, bias=False),
            nn.GroupNorm(8, out_channels),
        )
        self.skip = (nn.Identity() if in_channels == out_channels and stride == 1 else
                     nn.Conv1d(in_channels, out_channels, 1, stride, bias=False))

    def forward(self, x):
        return F.gelu(self.body(x) + self.skip(x))


class ResCNN64(nn.Module):
    def __init__(self, classes):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv1d(6, 32, 7, padding=3, bias=False), nn.GroupNorm(8, 32), nn.GELU(),
            ResidualBlock(32, 32, 5, 1),
            ResidualBlock(32, 64, 5, 2),
            ResidualBlock(64, 128, 3, 2),
        )
        self.embedding = nn.Sequential(nn.Linear(256, 128), nn.GELU(), nn.Dropout(.2), nn.Linear(128, 64))
        self.classifier = nn.Linear(64, classes, bias=False)

    def encode(self, x):
        features = self.features(x)
        pooled = torch.cat((features.mean(dim=-1), features.amax(dim=-1)), dim=1)
        return F.normalize(self.embedding(pooled), dim=1)

    def forward(self, x):
        return 12 * (self.encode(x) @ F.normalize(self.classifier.weight, dim=1).T)


ARCHITECTURES = {'simple16': OdorEncoder, 'rescnn64': ResCNN64}
