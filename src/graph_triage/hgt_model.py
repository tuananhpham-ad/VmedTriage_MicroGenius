"""Reusable Heterogeneous Graph Transformer encoder for patient graphs."""

from __future__ import annotations

import torch.nn.functional as functional
from torch import nn

from src.graph_triage.patient_graph import EDGE_TYPES, FEATURE_DIMENSION, NODE_TYPES


class HGTEncoder(nn.Module):
    """Encode each graph's implicit patient node into one graph embedding."""

    def __init__(self, hidden_channels: int, heads: int, layers: int, dropout: float):
        super().__init__()
        try:
            from torch_geometric.nn import HGTConv
        except ImportError as error:
            raise RuntimeError("HGT requires torch-geometric. Run: pip install -r requirements.txt") from error
        self.input_layers = nn.ModuleDict({node_type: nn.Linear(FEATURE_DIMENSION, hidden_channels) for node_type in NODE_TYPES})
        metadata = (list(NODE_TYPES), list(EDGE_TYPES))
        self.convolutions = nn.ModuleList([HGTConv(hidden_channels, hidden_channels, metadata, heads=heads) for _ in range(layers)])
        self.dropout = dropout

    def forward(self, x_dict, edge_index_dict):
        features = {node_type: functional.relu(self.input_layers[node_type](x_dict[node_type])) for node_type in NODE_TYPES}
        for convolution in self.convolutions:
            update = convolution(features, edge_index_dict)
            features = {
                node_type: functional.dropout(
                    functional.relu(update.get(node_type, features[node_type])),
                    p=self.dropout,
                    training=self.training,
                )
                for node_type in NODE_TYPES
            }
        return features["patient"]
