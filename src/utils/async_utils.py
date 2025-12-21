"""
Async utilities for bridging synchronous and asynchronous code.
"""

import asyncio
import functools
from typing import TypeVar, Callable, Any

T = TypeVar("T")

async def run_blocking(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """
    Run a blocking function in a separate thread to avoid blocking the event loop.
    
    Args:
        func: The blocking function to run.
        *args: Positional arguments for the function.
        **kwargs: Keyword arguments for the function.
        
    Returns:
        The result of the function call.
    """
    loop = asyncio.get_running_loop()
    partial_func = functools.partial(func, *args, **kwargs)
    return await loop.run_in_executor(None, partial_func)
