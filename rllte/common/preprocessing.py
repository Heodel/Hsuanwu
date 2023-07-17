# =============================================================================
# MIT License

# Copyright (c) 2023 Reinforcement Learning Evolution Foundation

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
# =============================================================================

from typing import Callable, Tuple, Dict, Union
from gymnasium import spaces
from torch.nn import functional as F

import gymnasium as gym
import numpy as np
import torch as th
import warnings


def process_env_info(observation_space: gym.Space, action_space: gym.Space) -> Tuple[Tuple, ...]:
    """Process the environment information.

    Args:
        observation_space (gym.Space): Observation space.
        action_space (gym.Space): Action space.

    Returns:
        Information of the observation and action space.
    """
    # observation part
    obs_shape = process_observation_space(observation_space)
    # action part
    action_shape, action_dim, action_type, action_range = process_action_space(action_space)

    return obs_shape, action_shape, action_dim, action_type, action_range


def process_observation_space(observation_space: gym.Space) -> Union[Tuple[int, ...], Dict[str, Tuple[int, ...]]]:
    """Process the observation space.
    
    Args:
        observation_space (gym.Space): Observation space.

    Returns:
        Information of the observation space.
    """
    if isinstance(observation_space, spaces.Box):
        # Observation is a vector
        return observation_space.shape
    elif isinstance(observation_space, spaces.Discrete):
        # Observation is an int
        return (1,)
    elif isinstance(observation_space, spaces.MultiDiscrete):
        # Number of discrete features
        return (int(len(observation_space.nvec)),)
    elif isinstance(observation_space, spaces.MultiBinary):
        # Number of binary features
        return observation_space.shape
    elif isinstance(observation_space, spaces.Dict):
        return {key: process_observation_space(subspace) for (key, subspace) in observation_space.spaces.items()}  # type: ignore[misc]

    else:
        raise NotImplementedError(f"{observation_space} observation space is not supported")
    

def process_action_space(action_space: gym.Space) -> Tuple[int, str, Union[int, float]]:
    """Get the dimension of the action space.

    Args:
        action_space (gym.Space): Action space.

    Returns:
        Information of the action space.
    """
    # TODO: revise the action_range
    action_shape = action_space.shape
    if action_space.__class__.__name__ == "Discrete":
        action_dim = int(action_space.n)
        action_type = "Discrete"
        action_range = [0, int(action_space.n) - 1]
    elif action_space.__class__.__name__ == "Box":
        action_dim = int(np.prod(action_space.shape))
        action_type = "Box"
        action_range = [
            float(action_space.low[0]),
            float(action_space.high[0]),
        ]
    elif action_space.__class__.__name__ == "MultiDiscrete":
        action_dim = int(len(action_space.nvec))
        action_type = "MultiDiscrete"
        action_range = [0, int(action_space.nvec[0]) - 1]
    elif action_space.__class__.__name__ == "MultiBinary":
        action_dim = int(action_space.shape[0])
        action_type = "MultiBinary"
        action_range = [0, 1]
    else:
        raise NotImplementedError(f"{action_space} action space is not supported")
    
    return action_shape, action_dim, action_type, action_range
    

def get_flattened_obs_dim(observation_space: spaces.Space) -> int:
    """Get the dimension of the observation space when flattened. It does not apply to image observation space.
        Borrowed from: https://github.com/DLR-RM/stable-baselines3/blob/master/stable_baselines3/common/preprocessing.py#L169

    Args:
        observation_space (spaces.Space): Observation space.

    Returns:
        The dimension of the observation space when flattened.
    """
    if isinstance(observation_space, spaces.MultiDiscrete):
        return sum(observation_space.nvec)
    else:
        # Use Gym internal method
        return spaces.utils.flatdim(observation_space)


def is_image_space_channels_first(observation_space: spaces.Box) -> bool:
    """Check if an image observation space (see ``is_image_space``)
        is channels-first (CxHxW, True) or channels-last (HxWxC, False).       
        Use a heuristic that channel dimension is the smallest of the three.
        If second dimension is smallest, raise an exception (no support).

        Borrowed from: https://github.com/DLR-RM/stable-baselines3/blob/master/stable_baselines3/common/preprocessing.py#L10
    
    Args:
        observation_space (spaces.Box): Observation space.

    Returns:
        True if observation space is channels-first image, False if channels-last.
    """
    smallest_dimension = np.argmin(observation_space.shape).item()
    if smallest_dimension == 1:
        warnings.warn("Treating image space as channels-last, while second dimension was smallest of the three.")
    return smallest_dimension == 0


def is_image_space(observation_space: gym.Space,
                   check_channels: bool = False,
                   normalized_image: bool = False
                   ) -> bool:
    """
    Check if a observation space has the shape, limits and dtype of a valid image.
    The check is conservative, so that it returns False if there is a doubt.
    Valid images: RGB, RGBD, GrayScale with values in [0, 255]

    Borrowed from: https://github.com/DLR-RM/stable-baselines3/blob/master/stable_baselines3/common/preprocessing.py#L27

    Args:
        observation_space (gym.Space): Observation space.
        check_channels (bool): Whether to do or not the check for the number of channels. 
            e.g., with frame-stacking, the observation space may have more channels than expected.
        normalized_image (bool): Whether to assume that the image is already normalized
            or not (this disables dtype and bounds checks): when True, it only checks that
            the space is a Box and has 3 dimensions.
            Otherwise, it checks that it has expected dtype (uint8) and bounds (values in [0, 255]).
    
    Returns:
        True if observation space is channels-first image, False if channels-last.
    """
    check_dtype = check_bounds = not normalized_image
    if isinstance(observation_space, spaces.Box) and len(observation_space.shape) == 3:
        # Check the type
        if check_dtype and observation_space.dtype != np.uint8:
            return False

        # Check the value range
        incorrect_bounds = np.any(observation_space.low != 0) or np.any(observation_space.high != 255)
        if check_bounds and incorrect_bounds:
            return False

        # Skip channels check
        if not check_channels:
            return True
        # Check the number of channels
        if is_image_space_channels_first(observation_space):
            n_channels = observation_space.shape[0]
        else:
            n_channels = observation_space.shape[-1]
        # GrayScale, RGB, RGBD
        return n_channels in [1, 3, 4]
    return False


def get_preprocess_obs_fn(observation_space: gym.Space) -> Callable:
    """Observations preprocessing function.
        Based on: https://github.com/DLR-RM/stable-baselines3/blob/master/stable_baselines3/common/preprocessing.py#L92

    Args:
        observation_space (gym.Space): Observation space.

    Returns:
        A function to preprocess observations.
    """
    def _multi_discrete_to_one_hot(obs: np.array) -> th.Tensor:
        obs = th.as_tensor(obs)
        return th.cat(
            [
                F.one_hot(obs_.long(), num_classes=int(observation_space.nvec[idx])).float()
                for idx, obs_ in enumerate(th.split(obs.long(), 1, dim=1))
            ],
            dim=-1,
        ).view(obs.shape[0], sum(observation_space.nvec))

    # Box observation space
    if isinstance(observation_space, spaces.Box):
        if is_image_space(observation_space):
            # image-based observations
            return lambda obs: th.as_tensor(obs) / 255.0
        else:
            # state-based observations
            return lambda obs: th.as_tensor(obs, dtype=th.float32)
    # Discrete observation space
    elif isinstance(observation_space, spaces.Discrete):
        return lambda obs: F.one_hot(th.as_tensor(obs).long(), num_classes=observation_space.n)
    # MultiDiscrete observation space
    elif isinstance(observation_space, spaces.MultiDiscrete):
        return _multi_discrete_to_one_hot
    # MultiBinary observation space
    elif isinstance(observation_space, spaces.MultiBinary):
        return lambda obs: th.as_tensor(obs).float()
    else:
        raise NotImplementedError(f"Preprocessing not implemented for {observation_space}")
