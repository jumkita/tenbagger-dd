from dataclasses import dataclass


@dataclass
class MarketSizeEstimate:
    """TAM/SAM/SOM 推計結果（単位は原則「億円」とシェア比率）。"""

    tam: float  # TAM（億円）
    sam: float  # SAM（億円）
    som_ratio: float  # SOM シェア（0〜1）
    reasoning: str

