"""
Common data structures and utilities for path planning algorithms.

This module provides shared components that can be reused across different 
search algorithms (e.g., A*, Dijkstra, EDA-A*).
"""

from typing import Dict, Optional, Tuple

class SearchNode:
    """
    Represent a node in the 4D search space (x, y, z, t).
    
    This class encapsulates the spatiotemporal coordinates, the physical state 
    vector (cumulative costs), and the algorithm-specific optimization variables.
    """
    
    DEFAULT_STATE = {
        'cum_distance': 0.0,
        'cum_time': 0.0,
        'absolute_time': 0.0,
        'cumulative_hazard': 0.0,   # H = -ln(P_surv); additive, avoids numerical underflow
        'p_survival': 1.0,          # derived: exp(-cumulative_hazard)
        'cum_fatality': 0.0,
        'cum_property': 0.0,
        'cum_noise': 0.0,
        'cum_objective': 0.0,       # Normalized cumulative objective J (论文 §3.4)
    }

    def __init__(
        self,
        x: int,
        y: int,
        z: int,
        t: int,
        state_dict: Optional[Dict[str, float]] = None,
        parent: Optional['SearchNode'] = None,
    ):
        """
        Initialize a search node.
        
        Args:
            x, y, z, t: Spatiotemporal grid indices.
            state_dict: Dictionary containing physical accumulation quantities:
                - cum_distance: Cumulative distance (m)
                - cum_time: Cumulative flight time (s)
                - p_survival: Survival probability [0, 1]
                - cum_fatality: Expected fatalities
                - cum_property: Property damage costs
                - cum_noise: Social noise impact
            parent: Reference to the parent node for path reconstruction.
        """
        # 1. Spatiotemporal coordinates: Inseparable 4D positioning
        self.coords = (x, y, z, t)
        self.x, self.y, self.z, self.t = x, y, z, t
        
        # 2. State dictionary: default physical accumulators plus optional metadata.
        self.state = dict(self.DEFAULT_STATE)
        if state_dict is not None:
            self.state.update(state_dict)
        
        # 3. Algorithm optimization variables (Standard for A*)
        self.g = 0.0  # Cost from start to current node
        self.f = 0.0  # Estimated total cost (g + h)
        
        # 4. Pointer
        self.parent = parent

    def __lt__(self, other: 'SearchNode') -> bool:
        """
        Comparison operator for priority queues based on the f-score.
        """
        return self.f < other.f

    def __repr__(self) -> str:
        return f"SearchNode(coords={self.coords}, f={self.f:.4f}, g={self.g:.4f})"

    @property
    def pos_3d(self) -> Tuple[int, int, int]:
        """Return spatial coordinates (x, y, z)."""
        return (self.x, self.y, self.z)


