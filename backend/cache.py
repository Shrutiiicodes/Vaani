import functools


def async_cache(maxsize: int = 256):
    """Memoise an async function on its positional args. None results are not cached.

    ponytail: the whole cache is dropped when full (no LRU order); swap for a real
    LRU if hit rates ever matter. Per-process only.
    """
    def deco(fn):
        store: dict = {}

        @functools.wraps(fn)
        async def wrapper(*args):
            if args in store:
                return store[args]
            result = await fn(*args)
            if result is not None:
                if len(store) >= maxsize:
                    store.clear()
                store[args] = result
            return result

        wrapper.cache = store
        return wrapper
    return deco
