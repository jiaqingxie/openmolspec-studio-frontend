"""Adjust proton peak positions using aligned spectra from similar training structures."""

import numpy as np
from rdkit import DataStructs
from scipy.optimize import linear_sum_assignment


class ProtonSpectrumLibrary:
    def __init__(self, path):
        with np.load(path, allow_pickle=False) as data:
            self.fingerprints = [
                DataStructs.CreateFromBinaryText(row.tobytes()) for row in data["words"]
            ]
            self.ends = data["ends"]
            self.ppm = data["ppm"]
        if len(self.fingerprints) < 8 or len(self.ends) != len(self.fingerprints) + 1:
            raise ValueError("Incomplete NMRGym training spectrum library")

    def nearest(self, features):
        fp = DataStructs.CreateFromBinaryText(np.packbits(features > 0).tobytes())
        similarities = np.asarray(
            DataStructs.BulkTanimotoSimilarity(fp, self.fingerprints)
        )
        cutoff = np.partition(similarities, -8)[-8]
        tied = np.flatnonzero(similarities >= cutoff)
        nearest = tied[np.argsort(-similarities[tied], kind="stable")[:8]]
        return nearest, similarities[nearest]

    def adjust(self, predicted, features, profile):
        indices, similarity = self.nearest(features)
        if not similarity[0]:
            return predicted
        spectra = [self.ppm[self.ends[i] : self.ends[i + 1]] for i in indices]
        weights = (similarity / similarity[0]) ** 12
        width = profile["width_ppm"]
        if profile["method"] == "assignment":
            total = np.zeros(len(predicted))
            support = np.zeros(len(predicted))
            for peaks, weight in zip(spectra, weights):
                distance = np.abs(predicted[:, None] - peaks)
                i, j = linear_sum_assignment(np.minimum(distance, 2 * width))
                delta = peaks[j] - predicted[i]
                reliability = weight * np.maximum(0, 1 - (delta / (2 * width)) ** 2)
                total[i] += reliability * delta
                support[i] += reliability
            correction = total / (support + 0.05 * sum(weights))
        elif profile["method"] == "density":
            peaks = np.concatenate(spectra)
            peak_weights = np.concatenate(
                [np.repeat(w / len(p), len(p)) for w, p in zip(weights, spectra)]
            )
            center = predicted.copy()
            for _ in range(3):
                diff = peaks[None, :] - center[:, None]
                local = np.exp(-0.5 * (diff / width) ** 2) * peak_weights
                center = np.clip(
                    center + (local * diff).sum(1) / (local.sum(1) + 1e-8),
                    predicted - 2 * width,
                    predicted + 2 * width,
                )
            correction = center - predicted
        else:
            raise ValueError("Unknown peak correction method")
        trust = np.clip((similarity[0] - 0.30) / 0.45, 0, 1)
        adjusted = np.sort(predicted + trust * correction)
        return (1 - profile["mix"]) * predicted + profile["mix"] * adjusted
