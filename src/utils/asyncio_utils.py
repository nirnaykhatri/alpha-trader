"""
Asyncio utility functions for handling blocking operations and event loops.
"""

import asyncio
import functools
from typing import TypeVar, Callable, Any, Optional
from src.core.logging_config import get_logger

logger = get_logger(__name__)

T = TypeVar('T')

async def run_blocking(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """
    Run a blocking function in a separate thread to avoid blocking the event loop.
    
    Args:
        func: The blocking function to run
        *args: Positional arguments for the function
        **kwargs: Keyword arguments for the function
        
    Returns:
        The result of the function call
    """
    loop = asyncio.get_running_loop()
    
    # functools.partial is needed to pass kwargs to run_in_executor
    # as it only accepts positional arguments
    if kwargs:
        func_call = functools.partial(func, *args, **kwargs)
        return await loop.run_in_executor(None, func_call)
    else:
        return await loop.run_in_executor(None, func, *args)
